const fs = require('fs');
const { parse } = require('json2csv');

const convertJsonToCsv = (jsonFilePath, csvFilePath) => {
  const jsonData = JSON.parse(fs.readFileSync(jsonFilePath, 'utf-8'));

  const fields = ['Target', 'VulnerabilityID', 'Severity', 'CVSS Score', 'Title', 'Library', 'Vulnerable Version', 'Fixed Version', 'Information URL'];
  const csvData = jsonData.Results.flatMap(result => {
    if (!result.Vulnerabilities) {
      console.warn(`No vulnerabilities found for target: ${result.Target}`);
      return [];
    }
    return result.Vulnerabilities.map(vulnerability => ({
      Target: result.Target,
      VulnerabilityID: vulnerability.VulnerabilityID || '',
      Severity: vulnerability.Severity || '',
      'CVSS Score': vulnerability.CVSS?.nvd?.V3Score || '',
      Title: vulnerability.Title || '',
      Library: vulnerability.PkgName || '',
      'Vulnerable Version': vulnerability.InstalledVersion || '',
      'Fixed Version': vulnerability.FixedVersion || '',
      'Information URL': vulnerability.PrimaryURL || ''
    }));
  });

  const csv = parse(csvData, { fields });
  fs.writeFileSync(csvFilePath, csv);
};

const [jsonFilePath, csvFilePath] = process.argv.slice(2);
convertJsonToCsv(jsonFilePath, csvFilePath);