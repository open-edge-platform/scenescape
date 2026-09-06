# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# flake8: noqa: E501

"""
This module provides functionality for parsing xUnit test result files and extracting detailed test outcomes, including executed tests and their statuses (passed, failed, or skipped).
The parsed data is structured to facilitate further processing or reporting of test results.

Function:
- parse_results: Parses an xUnit test results file and categorizes test cases based on their execution outcome.
"""

import re
import xml.etree.ElementTree as ET

KEY_REGEX = re.compile(r"(NEX-T\d{5,6}|NEX-\d{5,6})")

def _extract_key(text):
    if not text:
        return None
    m = KEY_REGEX.search(text)
    if m:
        return m.group(0)
    parts = text.split()
    return parts[0] if parts else None

def parse_results(path):
    """
    Parses xUnit test results from a file and organizes test case identifiers into categories based on their results.

    Parameters:
        path (str): The filesystem path to the xUnit result file to be parsed.

    Returns:
        tuple of lists: Contains four lists of test identifiers:
        - results_exec: All test cases that were executed.
        - results_pass: Test cases that passed.
        - results_fail: Test cases that failed.
        - results_skip: Test cases that were skipped.

    This function reads the specified xUnit results file, parses the contents, and then processes each test case to categorize them based on their outcomes.
    Each test case is identified by the method name associated with the test, which is expected to be in a specific format that includes the test identifier.
    """
    tree = ET.parse(path)
    root = tree.getroot()

    results_exec = []
    results_pass = []
    results_fail = []
    results_skip = []

    idx = 0
    for tc in root.iter('testcase'):
        idx += 1
        name = tc.get('name') or tc.get('classname') or f'unnamed-{idx}'
        # prefer extracting an explicit Jira-like key if present
        test_id = _extract_key(name) or name

        results_exec.append(test_id)

        if tc.find('failure') is not None or tc.find('error') is not None:
            results_fail.append(test_id)
        elif tc.find('skipped') is not None:
            results_skip.append(test_id)
        else:
            results_pass.append(test_id)

    return results_exec, results_pass, results_fail, results_skip
