import csv
from collections import defaultdict
import requests
import os

input_file = "SceneScape-1.4.0-deps.csv"
output_file = "third-party-programs-new.txt"
preamble_file = os.path.join("licenses", "preamble.txt")

components = []
licenses = set()
license_to_components = defaultdict(list)
failed_licenses = []
license_sources = {}  # license_name -> source (url, file, or None)

def get_license_url(license_name):
    spdx_base = "https://spdx.org/licenses/"
    custom_map = {
        "AFL-2.1 License": spdx_base + "AFL-2.1.txt",
        "Apache-2.0": spdx_base + "Apache-2.0.txt",
        "Artistic License": spdx_base + "Artistic-2.0.txt",
        "Artistic License 1.0": spdx_base + "Artistic-1.0.txt",
        "BSD License": spdx_base + "BSD-3-Clause.txt",
        "BSD-2-Clause": spdx_base + "BSD-2-Clause.txt",
        "BSD-3-Clause": spdx_base + "BSD-3-Clause.txt",
        "EPL-1.0": spdx_base + "EPL-1.0.txt",
        "EPL-2.0": spdx_base + "EPL-2.0.txt",
        "FTL": spdx_base + "FTL.txt",
        "GPL-1.0": spdx_base + "GPL-1.0-only.txt",
        "GPL-2.0": spdx_base + "GPL-2.0-only.txt",
        "GPL-3.0": spdx_base + "GPL-3.0-only.txt",
        "HPND": spdx_base + "HPND.txt",
        "ICU License": "https://spdx.org/licenses/ICU.txt",
        "ISC": spdx_base + "ISC.txt",
        "ISC License": spdx_base + "ISC.txt",
        "JBIG License": spdx_base + "JBIG.txt",
        "LGPL": spdx_base + "LGPL-2.1-only.txt",
        "LGPL-2.0": spdx_base + "LGPL-2.0-only.txt",
        "LGPL-2.1": spdx_base + "LGPL-2.1-only.txt",
        "LGPL-3.0": spdx_base + "LGPL-3.0-only.txt",
        "libpng License": spdx_base + "Libpng.txt",
        "MIT": spdx_base + "MIT.txt",
        "MPL-1.1": spdx_base + "MPL-1.1.txt",
        "MPL-2.0": spdx_base + "MPL-2.0.txt",
        "OpenLDAP Public License": spdx_base + "OLDAP-2.8.txt",
        "PIL": "https://spdx.org/licenses/HPND.txt",  # PIL uses HPND
        "PostgreSQL": spdx_base + "PostgreSQL.txt",
        "PSF": spdx_base + "Python-2.0.txt",
        "Qhull License": "https://spdx.org/licenses/Qhull.txt",
        "SIL Open Font License": spdx_base + "OFL-1.1.txt",
        "Unlicense": spdx_base + "Unlicense.txt",
        "X11": spdx_base + "X11.txt",
    }
    return custom_map.get(license_name, "")

def sanitize_filename(name):
    return name.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_").replace("\n", "_")

def download_license_text(license_name):
    url = get_license_url(license_name)
    if url:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                license_sources[license_name] = url
                return resp.text
        except Exception:
            pass
    local_filename = os.path.join("licenses", sanitize_filename(license_name) + ".txt")
    if os.path.isfile(local_filename):
        try:
            with open(local_filename, "r", encoding="utf-8") as lf:
                license_sources[license_name] = local_filename
                return lf.read()
        except Exception as e:
            failed_licenses.append(license_name)
            license_sources[license_name] = None
            return f"[Error reading local license file for {license_name}: {e}]"
    failed_licenses.append(license_name)
    license_sources[license_name] = None
    return f"[No license text available for {license_name}]"

with open(input_file, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        component = row["Component"].strip()
        license_ = row["License"].strip()
        components.append((component, license_))
        if license_:
            for lic in [l.strip() for l in license_.replace(" and ", ",").replace(" or ", ",").replace(" OR ", ",").split(",")]:
                if lic:
                    licenses.add(lic)
                    license_to_components[lic].append(component)

licenses_sorted = sorted(licenses, key=lambda x: x.lower())
for lic in licenses_sorted:
    license_to_components[lic] = sorted(set(license_to_components[lic]), key=lambda x: x.lower())

# Read preamble
preamble = ""
if os.path.isfile(preamble_file):
    with open(preamble_file, "r", encoding="utf-8") as pf:
        preamble = pf.read().rstrip() + "\n"

with open(output_file, "w", encoding="utf-8") as f:
    f.write(preamble)
    for idx, lic in enumerate(licenses_sorted, 1):
        f.write("\n\n")
        f.write("-------------------------------------------------------------\n")
        f.write(f"{idx}. Software released under the license {lic}:\n")
        for comp in license_to_components[lic]:
            f.write(f"    {comp}\n")
        f.write("\n")
        license_text = download_license_text(lic)
        f.write(license_text.strip() + "\n")

print("Unique licenses used (with source):")
for lic in licenses_sorted:
    src = license_sources.get(lic)
    if src is None:
        src_str = "None"
    elif src.startswith("http"):
        src_str = f"URL: {src}"
    else:
        src_str = f"File: {src}"
    print(f" - {lic} [{src_str}]")

if failed_licenses:
    print("\nFailed to obtain license text for the following licenses:")
    for lic in sorted(set(failed_licenses)):
        print(f" - {lic}")

print(f"\nGenerated {output_file}")
