const fs = require('fs');
const { parse } = require('json2csv');

const convertJsonToCsv = (jsonFilePath, csvFilePath) => {
  // Load JSON data
  const jsonData = JSON.parse(fs.readFileSync(jsonFilePath, 'utf-8'));

  // Debug: Print the loaded JSON data
  console.log("Loaded JSON data:", JSON.stringify(jsonData, null, 2));

  const fields = ['Target', 'VulnerabilityID', 'Severity', 'CVSS Score', 'Title', 'Library', 'Vulnerable Version', 'Fixed Version', 'Information URL'];
  const csvData = jsonData.Results.flatMap(result => {
    console.log(`Processing target: ${result.Target}`);  // Debug: Print the target being processed

    if (!result.Vulnerabilities) {
      console.warn(`No vulnerabilities found for target: ${result.Target}`);
      return [];
    }

    return result.Vulnerabilities.map(vulnerability => {
      console.log(`Processing vulnerability: ${vulnerability.VulnerabilityID}`);  // Debug: Print the vulnerability ID
      return {
        Target: result.Target,
        VulnerabilityID: vulnerability.VulnerabilityID || '',
        Severity: vulnerability.Severity || '',
        'CVSS Score': vulnerability.CVSS?.nvd?.V3Score || '',
        Title: vulnerability.Title || '',
        Library: vulnerability.PkgName || '',
        'Vulnerable Version': vulnerability.InstalledVersion || '',
        'Fixed Version': vulnerability.FixedVersion || '',
        'Information URL': vulnerability.PrimaryURL || ''
      };
    });
  });

  // Debug: Print the CSV data before writing
  console.log("CSV Data:", csvData);

  const csv = parse(csvData, { fields });
  fs.writeFileSync(csvFilePath, csv);
  console.log(`CSV file written to ${csvFilePath}`);
};

const [jsonFilePath, csvFilePath] = process.argv.slice(2);
convertJsonToCsv(jsonFilePath, csvFilePath);