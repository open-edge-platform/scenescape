#!/usr/bin/env python3
"""
ONVIF camera diagnostics built on the dlstreamer ONVIF libraries
(/home/fst/dlstreamer/python/dlstreamer/onvif).

Prints device identity and the advertised event topics, then drops into
a live loop that:
  - subscribes to camera events and prints the raw SOAP envelope for
    every notification received, and
  - on user request (press Enter), queries PTZ GetStatus and prints the
    Pan/Tilt/Zoom position plus MoveStatus.

Run with the venv that has the library installed, e.g.:
    /home/fst/dlstreamer/venv/bin/python3 onvif_diagnostics.py \\
        --ip 192.168.0.90 --user admin --password ...
"""
import argparse
import copy
import datetime
import os
import select
import sys

import requests  # pylint: disable=import-error
from lxml import etree
from onvif import ONVIFCamera  # pylint: disable=import-error
from onvif.client import ONVIFService, SERVICES  # pylint: disable=import-error
from zeep.plugins import HistoryPlugin, Plugin  # pylint: disable=import-error

from dlstreamer.onvif.camera_profiles import read_camera_profiles
from dlstreamer.onvif.event_manager import get_supported_event_topics
from dlstreamer.onvif.ptz import PTZController


class _Tee:
    """Duplicates writes to multiple streams (e.g. the terminal and a log file)."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data: str) -> None:
        for stream in self._streams:
            stream.write(data)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


def _start_run_log() -> str:
    """Tee stdout/stderr to a timestamped log file alongside this script; return its path."""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "onvif_logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_path = os.path.join(log_dir, f"onvif_diagnostics_{timestamp}.log")
    log_file = open(log_path, "w", encoding="utf-8")  # pylint: disable=consider-using-with
    sys.stdout = _Tee(sys.stdout, log_file)
    sys.stderr = _Tee(sys.stderr, log_file)
    return log_path


_GETDT_BODY = b"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
  <soap:Body><tds:GetSystemDateAndTime/></soap:Body>
</soap:Envelope>"""


def _fetch_camera_utc(host: str, port: int) -> datetime.datetime:
    """Read the camera's UTC clock via a plain, unauthenticated SOAP call."""
    resp = requests.post(
        f"http://{host}:{port}/onvif/device_service",
        data=_GETDT_BODY,
        headers={"Content-Type": "application/soap+xml; charset=utf-8"},
        proxies={"http": None, "https": None},
        timeout=5,
    )
    root = etree.fromstring(resp.content)
    ns = {"tt": "http://www.onvif.org/ver10/schema"}
    node = root.find(".//tt:UTCDateTime", ns)
    year, month, day = (int(node.find(f"tt:Date/tt:{f}", ns).text) for f in ("Year", "Month", "Day"))
    hour, minute, second = (int(node.find(f"tt:Time/tt:{f}", ns).text) for f in ("Hour", "Minute", "Second"))
    return datetime.datetime(year, month, day, hour, minute, second)


def _update_xaddrs_with_clock_skew_fix(self) -> None:
    """Replacement for ONVIFCamera.update_xaddrs that tolerates clock drift.

    This camera's WS-Security timestamp tolerance is ~5s and its onboard
    clock free-runs (no working NTP), drifting well past that, so every
    authenticated call gets rejected with 'Sender not authorized' even with
    correct credentials. onvif-zeep's own adjust_time=True can't fix this on
    Axis: its bootstrap GetSystemDateAndTime call goes through the same
    WS-Security-authenticated devicemgmt service, so it fails for the exact
    same reason (chicken-and-egg). Reading the time with a bare, unauthenticated
    request breaks that cycle. Also intentionally skips onvif-zeep's own
    auto-CreatePullPointSubscription probe (it silently leaks a subscription
    against this camera's MaxPullPoints=4 cap on every ONVIFCamera() call).
    """
    try:
        camera_utc = _fetch_camera_utc(self.host, self.port)
        self.dt_diff = camera_utc - datetime.datetime.utcnow()
    except Exception:  # pylint: disable=broad-exception-caught
        self.dt_diff = None
    self.devicemgmt = self.create_devicemgmt_service()
    self.xaddrs = {}
    capabilities = self.devicemgmt.GetCapabilities({"Category": "All"})
    for name in capabilities:
        capability = capabilities[name]
        try:
            if name.lower() in SERVICES and capability is not None:
                ns = SERVICES[name.lower()]["ns"]
                self.xaddrs[ns] = capability["XAddr"]
        except Exception:  # pylint: disable=broad-exception-caught
            pass


ONVIFCamera.update_xaddrs = _update_xaddrs_with_clock_skew_fix


class ReferenceParameterPlugin(Plugin):
    """Injects a subscription's WS-Addressing ReferenceParameters into requests.

    This camera dispatches every subscription through one shared endpoint
    (SubscriptionReference.Address is the same URL for all subscriptions)
    and instead identifies which subscription a call targets via a
    ReferenceParameters element (an Axis tnsaxis:SubscriptionId) returned by
    CreatePullPointSubscription. onvif-zeep/dlstreamer's OnvifEventEngine
    never captures or resends that element, so PullMessages/Unsubscribe
    fail with ter:InvalidArgs on this camera even though the subscription
    itself was created successfully.
    """

    def __init__(self, ref_params):
        self._ref_params = ref_params

    def egress(self, envelope, http_headers, operation, binding_options):
        soap_env = "http://www.w3.org/2003/05/soap-envelope"
        header = envelope.find(f"{{{soap_env}}}Header")
        if header is None:
            header = etree.SubElement(envelope, f"{{{soap_env}}}Header")
            envelope.insert(0, header)
        for el in self._ref_params:
            header.append(copy.deepcopy(el))
        return envelope, http_headers


def print_soap(title: str, xml_element) -> None:
    """Pretty-print a raw SOAP envelope."""
    if xml_element is None:
        return
    raw_xml = etree.tostring(xml_element, pretty_print=True, encoding="utf-8").decode("utf-8")
    print(f"\n{'=' * 25} [{title}] {'=' * 25}")
    print(raw_xml)
    print("=" * (52 + len(title)))


def print_device_info(ip: str, port: int, user: str, password: str) -> None:
    cam = ONVIFCamera(ip, port, user, password)
    info = cam.create_devicemgmt_service().GetDeviceInformation()
    print("\nCAMERA HARDWARE IDENTITY:")
    print(f"   Manufacturer     : {info.Manufacturer}")
    print(f"   Model            : {info.Model}")
    print(f"   Firmware Version : {info.FirmwareVersion}")
    print(f"   Serial Number    : {info.SerialNumber}")
    print(f"   Hardware Id      : {getattr(info, 'HardwareId', '-')}")


def print_event_topics(ip: str, port: int, user: str, password: str) -> None:
    topics = get_supported_event_topics(ip, port, user, password)
    print(f"\nSUPPORTED EVENT TOPICS ({len(topics)}):")
    if not topics:
        print("   (camera advertises no event topics)")
    for topic in topics:
        print(f"   - {topic.short()}")


def get_first_profile_token(ip: str, port: int, user: str, password: str) -> str:
    """Read this camera's media profiles and return the first profile token."""
    result = next(read_camera_profiles([{"hostname": ip, "port": port}], user, password))
    if result.error:
        raise RuntimeError(result.error)
    if not result.profiles:
        raise RuntimeError("camera reported no media profiles")
    return next(
        (profile.token for profile in result.profiles if getattr(profile, "ptz_token", "")),
        result.profiles[0].token,
    )


def query_ptz_status(ip: str, port: int, user: str, password: str, profile_token: str) -> None:
    """Issue GetStatus and print position + MoveStatus (or report why it failed)."""
    try:
        with PTZController(ip, port, profile_token, user, password) as ctrl:
            status = ctrl.get_status()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"\n[PTZ] GetStatus failed (camera may not support PTZ): {type(exc).__name__}: {exc}")
        return
    print("\nPTZ STATUS (GetStatus):")
    print(f"   Position   : pan={status.position.pan}, tilt={status.position.tilt}, zoom={status.position.zoom}")
    print(f"   MoveStatus : PanTilt={status.pan_tilt_move_status}, Zoom={status.zoom_move_status}")
    if status.error:
        print(f"   Error      : {status.error}")


def _stdin_has_input() -> bool:
    return bool(select.select([sys.stdin], [], [], 0)[0])


def event_loop(ip: str, port: int, user: str, password: str, profile_token: str | None) -> None:
    """Subscribe to events and print raw SOAP for each notification.

    Talks to the events/PullPoint services directly (not via OnvifEventEngine,
    which drops the ReferenceParameters this camera requires - see
    ReferenceParameterPlugin) so every request after CreatePullPointSubscription
    carries the subscription's SubscriptionId reference parameter. Always
    unsubscribes on exit: this camera caps concurrent PullPoint subscriptions
    at 4 (GetServiceCapabilities -> MaxPullPoints), and a script that never
    unsubscribes will exhaust the pool after a few runs.
    """
    cam = ONVIFCamera(ip, port, user, password)
    events = cam.create_events_service()
    response = events.CreatePullPointSubscription({"InitialTerminationTime": "PT1H"})
    subscription_address = response.SubscriptionReference.Address._value_1  # pylint: disable=protected-access
    ref_params_container = response.SubscriptionReference.ReferenceParameters
    # Only Axis-style shared-endpoint subscriptions carry reference parameters;
    # cameras using a unique per-subscription address (e.g. this TP-Link) omit them.
    ref_params = list(ref_params_container._value_1) if ref_params_container is not None else []  # pylint: disable=protected-access

    _, wsdl_file, _ = cam.get_definition("events")

    def _build_service(binding_name: str) -> ONVIFService:
        service = ONVIFService(
            xaddr=subscription_address,
            user=user,
            passwd=password,
            url=wsdl_file,
            encrypt=cam.encrypt,
            daemon=cam.daemon,
            no_cache=cam.no_cache,
            portType=None,
            dt_diff=cam.dt_diff,
            binding_name=binding_name,
            transport=cam.transport,
        )
        if ref_params:
            service.zeep_client.plugins.append(ReferenceParameterPlugin(ref_params))
        return service

    history = HistoryPlugin()
    pullpoint = _build_service("{http://www.onvif.org/ver10/events/wsdl}PullPointSubscriptionBinding")
    pullpoint.zeep_client.plugins.append(history)
    subscription_manager = _build_service("{http://www.onvif.org/ver10/events/wsdl}SubscriptionManagerBinding")

    print("\nListening for events... press Enter to query PTZ GetStatus, 'q' + Enter to quit.")
    try:
        while True:
            if _stdin_has_input():
                line = sys.stdin.readline().strip().lower()
                if line == "q":
                    break
                if profile_token:
                    query_ptz_status(ip, port, user, password, profile_token)
                else:
                    print("[PTZ] no media profile available, skipping GetStatus")

            try:
                response = pullpoint.PullMessages({"Timeout": "PT1S", "MessageLimit": 10})
            except Exception:  # pylint: disable=broad-exception-caught
                continue  # pull timeouts are normal when no events fire

            messages = getattr(response, "NotificationMessage", None) or []
            if messages and history.last_received:
                print_soap("EVENT: PullMessages response", history.last_received["envelope"])
    except KeyboardInterrupt:
        pass
    finally:
        print("\nUnsubscribing...")
        try:
            subscription_manager.Unsubscribe({})
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"(unsubscribe failed, ignoring: {exc})")


def main() -> None:
    log_path = _start_run_log()
    print(f"Logging this run to: {log_path}")

    parser = argparse.ArgumentParser(description="ONVIF camera diagnostics (info, events, PTZ status).")
    parser.add_argument("--ip", required=True, help="Camera IP address")
    parser.add_argument("--port", type=int, default=80, help="ONVIF port (default: 80)")
    parser.add_argument("--user", required=True, help="ONVIF username")
    parser.add_argument("--password", required=True, help="ONVIF password")
    args = parser.parse_args()

    print(f"Connecting to ONVIF camera at {args.ip}:{args.port}...")
    print_device_info(args.ip, args.port, args.user, args.password)
    print_event_topics(args.ip, args.port, args.user, args.password)

    profile_token = None
    try:
        profile_token = get_first_profile_token(args.ip, args.port, args.user, args.password)
        print(f"\nUsing media profile: {profile_token}")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"\n[WARN] Could not read media profiles: {exc}")

    if profile_token:
        query_ptz_status(args.ip, args.port, args.user, args.password, profile_token)

    event_loop(args.ip, args.port, args.user, args.password, profile_token)


if __name__ == "__main__":
    main()
