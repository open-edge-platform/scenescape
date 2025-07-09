import json
import csv
import argparse

def convert_json_to_csv(json_file_path, csv_file_path):
    # Load JSON data
    with open(json_file_path, 'r') as json_file:
        data = json.load(json_file)
    
    # Debug: Print the loaded JSON data
    print("Loaded JSON data:", json.dumps(data, indent=2))

    # Open CSV file for writing
    with open(csv_file_path, 'w', newline='') as csv_file:
        csv_writer = csv.writer(csv_file)

        # Write CSV header for vulnerabilities
        csv_writer.writerow(['Target', 'VulnerabilityID', 'Severity', 'CVSS Score', 'Title', 'Library', 'Vulnerable Version', 'Fixed Version', 'Information URL'])

        # Iterate over results and write vulnerabilities to CSV
        for result in data.get('Results', []):
            target = result.get('Target', '')
            print(f"Processing target: {target}")  # Debug: Print the target being processed
            for vulnerability in result.get('Vulnerabilities', []):
                print(f"Processing vulnerability: {vulnerability.get('VulnerabilityID', '')}")  # Debug: Print the vulnerability ID
                csv_writer.writerow([
                    target,
                    vulnerability.get('VulnerabilityID', ''),
                    vulnerability.get('Severity', ''),
                    vulnerability.get('CVSS', {}).get('nvd', {}).get('V3Score', ''),
                    vulnerability.get('Title', ''),
                    vulnerability.get('PkgName', ''),
                    vulnerability.get('InstalledVersion', ''),
                    vulnerability.get('FixedVersion', ''),
                    vulnerability.get('PrimaryURL', '')
                ])

        # Write CSV header for dependencies
        csv_writer.writerow(['Target', 'ID', 'Name', 'Version'])

        # Iterate over results and write dependencies to CSV
        for result in data.get('Results', []):
            target = result.get('Target', '')
            print(f"Processing target for dependencies: {target}")  # Debug: Print the target being processed for dependencies
            for package in result.get('Packages', []):
                print(f"Processing package: {package.get('ID', '')}")  # Debug: Print the package ID
                csv_writer.writerow([
                    target,
                    package.get('ID', ''),
                    package.get('Name', ''),
                    package.get('Version', '')
                ])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Convert Trivy JSON scan results to CSV.')
    parser.add_argument('json_file', help='Path to the JSON file containing Trivy scan results.')
    parser.add_argument('csv_file', help='Path to the output CSV file.')

    args = parser.parse_args()

    convert_json_to_csv(args.json_file, args.csv_file)