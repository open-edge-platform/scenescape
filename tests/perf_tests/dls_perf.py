#!/usr/bin/env python3
import subprocess
import argparse
import json
import re
from datetime import datetime, timezone

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="scenescape-retail-video-1", help="Container name")
    parser.add_argument("--since", default="5m", help="How far back to fetch logs (e.g., 10m, 1h)")
    parser.add_argument("--threshold", type=float, default=10.0, help="FPS threshold for 'FELL BEHIND'")
    parser.add_argument("--target", type=float, help="Target FPS rate to verify pass/fail")
    return parser.parse_args()

def get_logs(container, since):
    print(f"Reading logs from container: {container}")
    try:
        cmd = ["docker", "logs", f"--since={since}", container]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        logs = result.stdout + result.stderr
        return logs
    except Exception as e:
        print(f"Failed to get logs: {e}")
        return ""

def extract_json_objects(log_data):
    # Split between JSON objects: }{
    parts = re.split(r'}\s*{', log_data)
    clean_jsons = []
    for i, part in enumerate(parts):
        # Add back the missing braces
        if not part.startswith('{'):
            part = '{' + part
        if not part.endswith('}'):
            part = part + '}'
        try:
            obj = json.loads(part)
            if 'fps' in obj and 'postdecode_timestamp' in obj:
                clean_jsons.append(obj)
        except json.JSONDecodeError:
            continue
    return clean_jsons

def calculate_stats(fps_entries, threshold):
    if not fps_entries:
        return None, None, 0

    times = []
    fell_behind = 0

    for entry in fps_entries:
        ts = entry["postdecode_timestamp"]
        fps = float(entry["fps"])
        try:
            ts_obj = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            times.append(ts_obj)
            if fps < threshold:
                fell_behind += 1
        except ValueError:
            continue

    if len(times) < 2:
        return None, None, fell_behind

    # Sort times
    times.sort()
    duration = (times[-1] - times[0]).total_seconds()
    msg_count = len(times)

    if duration == 0:
        return None, None, fell_behind

    final_rate = msg_count / duration
    time_per_msg = (duration / msg_count) * 1000  # in ms

    return round(final_rate, 2), round(time_per_msg, 2), fell_behind

def main():
    args = parse_args()
    logs = get_logs(args.container, args.since)
    entries = extract_json_objects(logs)

    if not entries:
        print(f"No FPS entries found in the last {args.since} of logs.")
        return

    final_rate, final_time, fell_behind = calculate_stats(entries, args.threshold)

    if final_rate is None:
        print("Not enough data to calculate rate.")
        return

    print(f"Time per msg: {final_time} ms, RATE: {final_rate} messages/s, {fell_behind} FELL BEHIND messages observed.")

    if args.target:
        if final_rate >= args.target:
            print(f"Reached at least {args.target} mps! ✅")
        else:
            print(f"Failed to reach minimum rate of {args.target} mps! ❌")

if __name__ == "__main__":
    main()

