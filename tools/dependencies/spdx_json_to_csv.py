#!/usr/bin/env python3
import json
import sys


COLUMN_NAMES=['Image', 'Component', 'Origin', 'License']

def load_spdx_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def normalize_license(lic):
    return lic.strip() if lic else "NOASSERTION"

def write_package_csv(image_name, spdx_doc, output_path):
    doc = spdx_doc["predicate"]
    packages = doc.get("packages", [])
    rows = []
    for pkg in packages:
        name = pkg.get("name", "UNKNOWN")
        version = pkg.get("versionInfo", "")
        spdxid = pkg.get("SPDXID", "")
        component = f"{name}:{version}"
        origin = "UNKNOWN"
        if spdxid.startswith("SPDXRef-Package-deb"):
            origin = "Ubuntu"
        elif spdxid.startswith("SPDXRef-Package-python"):
            origin = "pypi"
            component = f"{name}=={version}"
        lic_expr = normalize_license(pkg.get("licenseDeclared"))
        rows.append([image_name, component, origin, lic_expr])

    # Write output file
    with open(output_path, "w", encoding="utf-8") as out:
        out.write(",".join(COLUMN_NAMES) + "\n")
        for row in rows:
            out.write(",".join(row) + "\n")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <image name> <output csv file> <input SPDX JSON file>")
        sys.exit(1)

    image_name = sys.argv[1]
    output_file = sys.argv[2]
    spdx_file = sys.argv[3]

    spdx_doc = load_spdx_file(spdx_file)
    write_package_csv(image_name, spdx_doc, output_file)
