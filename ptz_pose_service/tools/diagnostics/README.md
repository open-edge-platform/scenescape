# ONVIF Camera Diagnostics (`onvif_diagnostics.py`)

Connects to an ONVIF camera and prints device identity, the camera's
advertised event topics, PTZ status (position + MoveStatus) on demand, and
a live event subscription that prints the raw SOAP envelope for every
notification received.

Built on top of the `dlstreamer.onvif` libraries
(`dlstreamer/python/dlstreamer/onvif`) for device profiles/PTZ/event-topic
discovery, plus direct `onvif-zeep` calls for the parts those libraries
don't cover (device info, raw SOAP event capture, and two Axis-specific
compatibility fixes — see **Known quirks** below).

## Requirements

- Python 3.10+
- A clone of the `dlstreamer` repo (for the `dlstreamer.onvif` package):
  ```bash
  git clone <dlstreamer-repo-url> ~/dlstreamer
  ```
- A virtualenv with the package and its ONVIF dependencies installed:
  ```bash
  cd ~/dlstreamer
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip setuptools wheel
  pip install -e python/
  pip install onvif-zeep zeep requests
  ```
- Network connectivity from this machine to the camera's IP on port 80
  (ONVIF/HTTP). Discovery (WS-Discovery/multicast) is **not** required —
  this script connects directly to a known IP, unlike
  `samples/ptz_sample`, which does use discovery to find cameras.

## Camera-side configuration

1. **Network reachability** — confirm the camera's actual IP first (don't
   assume the IP printed on a label/sticker or a stale config is correct).
   `ping`/`arp -a` and mDNS (`avahi-resolve -n <hostname>.local`) can help
   locate it if it's on a directly-attached subnet.
2. **An ONVIF-capable account** — create/confirm a user with Administrator
   role. On Axis cameras this is usually the same account used for the web
   UI and VAPIX, but ONVIF authorization has occasionally needed a
   dedicated check under **System → ONVIF** on some firmware versions —
   if you get an authorization error despite correct credentials, verify
   there too.
3. **ONVIF service enabled** — make sure ONVIF/VAPIX Web Service access is
   turned on for the device (enabled by default on most Axis firmware).
4. **Clock** — the camera's clock should be reasonably in sync with this
   host (WS-Security rejects requests whose timestamp is too far from the
   camera's own clock; the tolerance can be as tight as ~5 seconds on some
   firmware). This script works around a broken/drifting camera clock
   automatically (see **Known quirks**), so this is a nice-to-have, not a
   hard requirement.
5. **No proxy for the camera's IP** — if this machine uses an HTTP(S)
   proxy (e.g. behind a corporate network), make sure the camera's IP is
   excluded, otherwise ONVIF calls silently get routed through the proxy
   and fail:
   ```bash
   export NO_PROXY="localhost,127.0.0.1,<camera-ip>"
   export no_proxy="$NO_PROXY"
   ```

## Running

```bash
export NO_PROXY="localhost,127.0.0.1,<camera-ip>"; export no_proxy="$NO_PROXY"
~/dlstreamer/venv/bin/python3 onvif_diagnostics.py \
  --ip <camera-ip> --port 80 --user <onvif-user> --password <onvif-password>
```

What happens:
1. Prints manufacturer/model/firmware/serial number.
2. Lists every event topic the camera advertises (`GetEventProperties`).
3. Reads the first media profile and queries PTZ `GetStatus`
   (position + MoveStatus) once. Cameras without a physical PTZ motor may
   still support this via their ONVIF PTZ node; if not, the script reports
   the failure and continues instead of crashing.
4. Subscribes to camera events and enters a loop:
   - Press **Enter** at any time to re-query PTZ `GetStatus`/MoveStatus.
   - Type **q** + Enter to quit (this always unsubscribes on the way out,
     including on Ctrl+C).
   - Any event notification received is printed as its raw SOAP XML.

## Logs

Each run writes a full transcript (everything printed to the console,
including tracebacks) to `onvif_logs/onvif_diagnostics_<timestamp>.log`
next to the script.

## Known quirks (discovered against an AXIS P3225-VE Mk II)

These aren't ONVIF-standard behavior, but this script works around them
so you normally don't need to do anything — listed here in case you hit
similar symptoms with a different tool:

- **Clock drift breaks WS-Security auth.** If the camera's clock isn't
  NTP-synced, authenticated ONVIF calls fail with
  `Sender not authorized` even with correct credentials, once the drift
  exceeds the firmware's timestamp tolerance. The script computes a
  client-side clock offset from an unauthenticated `GetSystemDateAndTime`
  call and applies it to every request, so a drifting camera clock is
  not a blocker.
- **Shared subscription endpoint.** This camera dispatches all event
  subscriptions through one shared URL and identifies which subscription
  a request is for via a WS-Addressing reference parameter
  (`SubscriptionId`) returned by `CreatePullPointSubscription`. Without
  resending that parameter on every `PullMessages`/`Unsubscribe` call,
  the camera rejects them with `ter:InvalidArgs` even though the
  subscription exists. The script captures and resends it.
- **`MaxPullPoints: 4`.** The Events service caps concurrent PullPoint
  subscriptions at 4 (`GetServiceCapabilities`). The script always
  unsubscribes on exit (including Ctrl+C) to avoid exhausting this pool;
  if you see `SubscribeCreationFailedFault` after killing a script
  ungracefully several times, a camera reboot clears stuck subscriptions.
- **Delayed-auth lockout.** Several failed logins in a row (any auth
  scheme) can make the camera temporarily reject even correct credentials.
  If you hit an authorization error right after a burst of failed
  attempts, wait a few minutes before retrying rather than repeating the
  attempt immediately.
