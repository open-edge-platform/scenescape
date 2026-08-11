# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# flake8: noqa: E501

"""
This module provides functionality for parsing xUnit test result files and extracting detailed test outcomes, including executed tests and their statuses (passed, failed, or skipped).
The parsed data is structured to facilitate further processing or reporting of test results.

Function:
- parse_results: Parses an xUnit test results file and categorizes test cases based on their execution outcome.
"""

import xunitparser


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

    This function reads the specified xUnit results file, uses xunitparser to parse the contents, and then processes each test case to categorize them based on their outcomes.
    Each test case is identified by the method name associated with the test, which is expected to be in a specific format that includes the test identifier.
    """
    with open(path) as fh:
        ts, tr = xunitparser.parse(fh)

    results_exec = []
    results_pass = []
    results_fail = []
    results_skip = []

    for tc in ts:
        test_id = tc.methodname.split(':')[0]
        results_exec.append(test_id)
        if tc.success:
            results_pass.append(test_id)
        elif tc.skipped:
            results_skip.append(test_id)
        else:
            results_fail.append(test_id)

    return results_exec, results_pass, results_fail, results_skip
