# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
import csv
import sys
import os

def load_epss_scores(epss_file):
    epss_scores = {}
    with open(epss_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cve = row.get('cve')
            score = row.get('epss')
            if cve and score:
                epss_scores[cve.upper()] = float(score)
    return epss_scores

def extract_cves(input_file):
    cves = set()
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('CVE-'):
                cves.add(line.split()[0].upper())
            else:
                # Try to find CVEs in the line
                for part in line.split():
                    if part.startswith('CVE-'):
                        cves.add(part.upper())
    return sorted(cves)

def write_report(cves, epss_scores, output_file):
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("CVE,EPSS_Score\n")
        for cve in cves:
            score = epss_scores.get(cve, "N/A")
            f.write(f"{cve},{score}\n")

def main():
    parser = argparse.ArgumentParser(description="Run EPSS Check")
    parser.add_argument('--input', required=True, help='Input file containing CVEs')
    parser.add_argument('--epss-data', required=True, help='EPSS CSV file')
    parser.add_argument('--output', required=True, help='Output report file')
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.epss_data):
        print(f"EPSS data file not found: {args.epss_data}", file=sys.stderr)
        sys.exit(1)

    epss_scores = load_epss_scores(args.epss_data)
    cves = extract_cves(args.input)
    write_report(cves, epss_scores, args.output)

if __name__ == "__main__":
    main()