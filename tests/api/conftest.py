# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
conftest.py - Custom pytest configuration for clean XML output
This generates Robot Framework-style minimal XML directly from pytest
"""

import pytest
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import requests
import os
from mapping_client import MappingClient
from scene_common.rest_client import RESTClient


class CleanXMLReporter:
  """Custom pytest plugin to generate clean, minimal JUnit XML"""

  def __init__(self):
    self.test_results = []
    self.start_time = None

  def pytest_sessionstart(self, session):
    """Called at the start of test session"""
    self.start_time = time.time()

  @pytest.hookimpl(hookwrapper=True)
  def pytest_runtest_makereport(self, item, call):
    """Capture test results"""
    outcome = yield
    report = outcome.get_result()

    # Only process the actual test call (not setup/teardown)
    if report.when == 'call':
      # Extract test name from item
      test_name = item.nodeid

      # If using parametrize, the name will be in item.name
      if hasattr(item, 'name'):
        test_name = item.name

      # Extract just the parameter part if exists
      # Format: test_api_scenario[Test Name Here]
      if '[' in test_name and ']' in test_name:
        test_name = test_name.split('[', 1)[1].rsplit(']', 1)[0]

      result = {
          'name': test_name,
          'classname': 'VisionAI_API_Tests',
          'time': report.duration,
          'outcome': report.outcome,  # 'passed', 'failed', 'skipped'
          'error_message': str(report.longrepr) if report.failed else None
      }

      self.test_results.append(result)

  def pytest_sessionfinish(self, session):
    """Generate clean XML at the end of session"""
    if not hasattr(session.config, 'workerinput'):  # Skip in xdist workers
      self._generate_clean_xml(session)

  def _generate_clean_xml(self, session):
    """Create minimal JUnit XML file"""
    # Get output path from pytest config
    xml_path = session.config.option.xmlpath
    if not xml_path:
      return  # No XML output requested

    # Calculate totals
    total_tests = len(self.test_results)
    passed = sum(1 for r in self.test_results if r['outcome'] == 'passed')
    failed = sum(1 for r in self.test_results if r['outcome'] == 'failed')
    skipped = sum(1 for r in self.test_results if r['outcome'] == 'skipped')
    errors = 0  # pytest doesn't distinguish errors from failures
    total_time = sum(r['time'] for r in self.test_results)

    # Create testsuite element
    testsuite = ET.Element('testsuite', {
        'name': 'VisionAI_API_Tests',
        'tests': str(total_tests),
        'errors': str(errors),
        'failures': str(failed),
        'skipped': str(skipped),
        'time': f'{total_time:.3f}'
    })

    # Add each test case
    for result in self.test_results:
      testcase = ET.SubElement(testsuite, 'testcase', {
          'classname': result['classname'],
          'name': result['name'],
          'time': f"{result['time']:.3f}"
      })

      # Only add failure element if test failed (optional)
      # Comment out the following block to have completely clean XML
      if result['outcome'] == 'failed':
        failure = ET.SubElement(testcase, 'failure', {
            'message': 'Test failed'
        })
      elif result['outcome'] == 'skipped':
        ET.SubElement(testcase, 'skipped')

    # Pretty print and save
    xml_str = ET.tostring(testsuite, encoding='unicode')
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent='  ')

    # Remove extra blank lines
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    clean_xml = '\n'.join(lines)

    # Write to file
    with open(xml_path, 'w', encoding='utf-8') as f:
      f.write(clean_xml)

    print(f"\n✓ Clean XML report generated: {xml_path}")
    print(
        f"  Total: {total_tests}, Passed: {passed}, Failed: {failed}, Skipped: {skipped}")


def pytest_configure(config):
  """Register the clean XML reporter plugin"""
  # Only register if XML output is requested
  if config.option.xmlpath:
    # Unregister default junitxml plugin
    if hasattr(config, '_xml'):
      config.pluginmanager.unregister(config._xml)

    # Register our custom clean reporter
    clean_reporter = CleanXMLReporter()
    config.pluginmanager.register(clean_reporter, 'cleanxml')
    config._cleanxml = clean_reporter


def pytest_addoption(parser):
  parser.addoption("--file", default=None,
                   help="Specific scenario file to run (e.g., 'scenarios/scene.json')")
  parser.addoption("--test_case", default=None,
                   help="Specific test case name to run")

@pytest.fixture(scope='session')
def base_url():
  return os.environ.get("API_BASE_URL", "https://localhost")

@pytest.fixture(scope='session')
def username():
  return os.environ.get("API_USERNAME", "admin")

@pytest.fixture(scope='session')
def password():
  return os.environ.get("SUPASS", "admin")

@pytest.fixture(scope='session')
def token(base_url, username, password):
  """Fetch authentication token from the SceneScape API"""
  response = requests.post(
    f"{base_url}/api/v1/auth",
    data={"username": username, "password": password},
    verify=False,
    timeout=10,
  )
  response.raise_for_status()
  api_token = response.json()["token"]
  return api_token

@pytest.fixture(scope='session')
def http_client(token, base_url) -> RESTClient:
  return RESTClient(url=f"{base_url}/api/v1", token=token, verify_ssl=False)

@pytest.fixture(scope='session')
def autocalib_client(token, base_url) -> RESTClient:
  return RESTClient(url=f"{base_url}/v1", token=token, verify_ssl=False)

@pytest.fixture(scope='session')
def mapping_client(token, base_url) -> MappingClient:
  return MappingClient(url=f"{base_url}:8444", token=token, verify_ssl=False)

@pytest.fixture(scope='session')
def api_map(http_client, autocalib_client, mapping_client):
  """Map API names to their respective clients"""
  return {
    "scene": http_client,
    "camera": http_client,
    "sensor": http_client,
    "region": http_client,
    "tripwire": http_client,
    "user": http_client,
    "asset": http_client,
    "child": http_client,
    "autocalibration": autocalib_client,
    "mapping": mapping_client,
}
