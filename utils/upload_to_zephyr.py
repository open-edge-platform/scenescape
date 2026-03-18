# SPDX-FileCopyrightText: (C) 2023 Intel Corporation
#
# SPDX-License-Identifier: LicenseRef-Intel

import argparse
import logging
import os
import sys

import libraries.jira as jira
import libraries.xunit as xunit

logging.basicConfig(level=logging.INFO)


def upload_zephyr_results(path, jira_token, folder_name, cycle_name, create, comment):

    results, results_pass, results_fail, results_skip = xunit.parse_results(path)

    j = jira.Jira(jira_token)
    test_from_jira = j.get_all_tests_as_lut(fields="name,key")
    logging.info(f"Retrieved {len(test_from_jira)} tests from Jira")
    assignees = {t['key'] for t in test_from_jira.values()}

    try:
        list_of_testcases_pass = [test_from_jira[lp_key]['key'] for lp_key in results_pass]
        list_of_testcases_fail = [test_from_jira[lp_key]['key'] for lp_key in results_fail]
    except KeyError as e:
        raise jira.JiraException(f'Test case with key "{e.args[0]}" not found in Jira')

    if create:
        method = j.create_test_cycle_results
    else:
        method = j.update_test_cycle_results
    method(folder_name, cycle_name, comment, assignees,
           list_of_testcases_pass, list_of_testcases_fail, [])


def main():
    parser = argparse.ArgumentParser(
        description="Upload robot results to jira"
    )
    parser.add_argument('--debug',
                        help="Debug",
                        action='store_true')

    parser.add_argument('-a', '--jira-token',
                        help="Jira API personal access token",
                        required=True,
                        action='store')

    parser.add_argument('-F', '--folder',
                        help="Folder to upload results to",
                        default=None,
                        action='store')

    parser.add_argument('-C', '--cycle',
                        help="Cycle to upload results to",
                        default=None,
                        action='store')

    parser.add_argument('-x', '--create-new-executions',
                        dest='create',
                        help="Create new executions for the test cycle",
                        default=False,
                        action='store_true')

    parser.add_argument('--comment',
                        help="Comment to add to the test executions",
                        default=None,
                        action='store')

    parser.add_argument(
        "path",
        help="Path to markdown files to check",
        type=str,
        action="store")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if not os.path.exists(args.path):
        print("Path {} not found".format(args.path))
        sys.exit(2)

    try:
        upload_zephyr_results(args.path, args.jira_token, args.folder, args.cycle, args.create, args.comment)
    except jira.JiraException as e:
        print()
        print(f"ERROR: {e}")
        print("Exiting due to Jira Exception")
        exit(1)


if __name__ == "__main__":
    main()