#!/usr/bin/env python3
"""
Upload pytest JUnit XML results to Jira Zephyr Scale
Usage: python upload_to_zephyr.py test-results.xml
"""

import requests
import xml.etree.ElementTree as ET
import json
import os
import sys
from datetime import datetime
from typing import List, Dict

# ===============================
# Configuration
# ===============================
ZEPHYR_API_URL = os.environ.get(
    "ZEPHYR_API_URL", 
    "https://api.zephyrscale.smartbear.com/v2"
)
ZEPHYR_API_TOKEN = os.environ.get("ZEPHYR_API_TOKEN")
PROJECT_KEY = os.environ.get("ZEPHYR_PROJECT_KEY", "VISIONAI")

# Status mapping: pytest -> Zephyr Scale
STATUS_MAP = {
    'passed': 'Pass',
    'failed': 'Fail',
    'skipped': 'Not Executed',
    'error': 'Fail'
}


class ZephyrUploader:
    """Handle uploading test results to Zephyr Scale"""
    
    def __init__(self, api_url: str, api_token: str, project_key: str):
        if not api_token:
            raise ValueError("ZEPHYR_API_TOKEN environment variable is required")
        
        self.api_url = api_url
        self.project_key = project_key
        self.headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json'
        }
    
    def parse_junit_xml(self, xml_file: str) -> List[Dict]:
        """Parse JUnit XML and extract test results"""
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        results = []
        
        # Handle both single testsuite and testsuites wrapper
        testsuites = root.findall('.//testsuite')
        if not testsuites:
            testsuites = [root] if root.tag == 'testsuite' else []
        
        for testsuite in testsuites:
            for testcase in testsuite.findall('testcase'):
                name = testcase.get('name', '')
                classname = testcase.get('classname', '')
                time = testcase.get('time', '0')
                
                # Extract test ID from name (if using parametrize with ids)
                # Format: test_api_scenario[test_id]
                test_id = name
                if '[' in name and ']' in name:
                    test_id = name.split('[')[1].rstrip(']')
                
                # Determine status
                if testcase.find('failure') is not None:
                    status = 'failed'
                    error_msg = testcase.find('failure').get('message', '')
                elif testcase.find('error') is not None:
                    status = 'error'
                    error_msg = testcase.find('error').get('message', '')
                elif testcase.find('skipped') is not None:
                    status = 'skipped'
                    error_msg = testcase.find('skipped').get('message', '')
                else:
                    status = 'passed'
                    error_msg = None
                
                # Extract custom properties if available
                properties = {}
                props_elem = testcase.find('properties')
                if props_elem is not None:
                    for prop in props_elem.findall('property'):
                        properties[prop.get('name')] = prop.get('value')
                
                results.append({
                    'test_id': test_id,
                    'name': name,
                    'classname': classname,
                    'status': status,
                    'zephyr_status': STATUS_MAP.get(status, 'Not Executed'),
                    'duration': float(time),
                    'error_message': error_msg,
                    'properties': properties
                })
        
        return results
    
    def create_test_cycle(self, name: str = None) -> str:
        """Create a new test cycle in Zephyr Scale"""
        if name is None:
            name = f'API Test Run - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        
        payload = {
            'projectKey': self.project_key,
            'name': name,
            'description': 'Automated API test execution from pytest'
        }
        
        try:
            response = requests.post(
                f'{self.api_url}/testcycles',
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            cycle_data = response.json()
            cycle_key = cycle_data.get('key')
            print(f"✓ Created test cycle: {cycle_key} - {name}")
            return cycle_key
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to create test cycle: {e}")
            if hasattr(e.response, 'text'):
                print(f"  Response: {e.response.text}")
            raise
    
    def upload_test_execution(self, test_result: Dict, cycle_key: str) -> bool:
        """Upload a single test execution result"""
        # Use test_id as the test case key
        # You may need to map test_id to actual Zephyr test case keys
        test_case_key = test_result.get('properties', {}).get('test_key', test_result['test_id'])
        
        payload = {
            'projectKey': self.project_key,
            'testCycleKey': cycle_key,
            'testCaseKey': test_case_key,
            'statusName': test_result['zephyr_status'],
            'executionTime': int(test_result['duration'] * 1000),  # Convert to milliseconds
        }
        
        # Add comment if test failed
        if test_result['error_message']:
            payload['comment'] = f"Error: {test_result['error_message'][:500]}"  # Limit length
        
        try:
            response = requests.post(
                f'{self.api_url}/testexecutions',
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            print(f"  ✓ {test_case_key}: {test_result['zephyr_status']} ({test_result['duration']:.2f}s)")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"  ✗ {test_case_key}: Failed - {e}")
            if hasattr(e.response, 'text'):
                print(f"    Response: {e.response.text}")
            return False
    
    def upload_results(self, xml_file: str, cycle_name: str = None):
        """Main method to parse XML and upload all results"""
        print(f"\n{'='*60}")
        print(f"Zephyr Scale Upload - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        
        print(f"📄 Parsing: {xml_file}")
        results = self.parse_junit_xml(xml_file)
        
        if not results:
            print("⚠️  No test results found in XML file")
            return
        
        print(f"📊 Found {len(results)} test results")
        
        # Summary
        passed = sum(1 for r in results if r['status'] == 'passed')
        failed = sum(1 for r in results if r['status'] in ['failed', 'error'])
        skipped = sum(1 for r in results if r['status'] == 'skipped')
        
        print(f"   ✓ Passed:  {passed}")
        print(f"   ✗ Failed:  {failed}")
        print(f"   ⊘ Skipped: {skipped}\n")
        
        # Create test cycle
        print("🔄 Creating test cycle...")
        cycle_key = self.create_test_cycle(cycle_name)
        
        # Upload each result
        print(f"\n📤 Uploading test executions to cycle {cycle_key}...")
        
        success_count = 0
        for i, result in enumerate(results, 1):
            print(f"[{i}/{len(results)}]", end=" ")
            if self.upload_test_execution(result, cycle_key):
                success_count += 1
        
        # Final summary
        print(f"\n{'='*60}")
        print(f"Upload Summary:")
        print(f"  Total tests:      {len(results)}")
        print(f"  Successfully uploaded: {success_count}")
        print(f"  Failed to upload:      {len(results) - success_count}")
        print(f"  Test Cycle:       {cycle_key}")
        print(f"{'='*60}\n")
        
        if success_count == len(results):
            print("✓ All results uploaded successfully!")
        else:
            print(f"⚠️  {len(results) - success_count} results failed to upload")


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python upload_to_zephyr.py <junit-xml-file> [cycle-name]")
        print("\nEnvironment variables required:")
        print("  ZEPHYR_API_TOKEN     - Your Zephyr Scale API token")
        print("  ZEPHYR_PROJECT_KEY   - Your Jira project key (default: VISIONAI)")
        print("  ZEPHYR_API_URL       - Zephyr API URL (default: https://api.zephyrscale.smartbear.com/v2)")
        sys.exit(1)
    
    xml_file = sys.argv[1]
    cycle_name = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(xml_file):
        print(f"Error: File not found: {xml_file}")
        sys.exit(1)
    
    try:
        uploader = ZephyrUploader(
            api_url=ZEPHYR_API_URL,
            api_token=ZEPHYR_API_TOKEN,
            project_key=PROJECT_KEY
        )
        uploader.upload_results(xml_file, cycle_name)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
