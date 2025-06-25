import json
import subprocess
import pprint

json_file = 'reuse_lint.json'  # Change this to your JSON file path


with open(json_file, 'r') as f:
    data = json.load(f)

pprint.pp(data)

for item in data.get("non_compliant").get("missing_copyright_info", []):
    print(f"Adding license to {item}")
    subprocess.run(["make", "add-licensing", "FILE=" + item])