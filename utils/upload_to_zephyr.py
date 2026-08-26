# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging
import os
import sys

import libraries.jira as jira
import libraries.xunit as xunit

logging.basicConfig(level=logging.INFO)


def upload_zephyr_results(
        path,
        jira_token,
        folder_name,
        cycle_name,
        cycle_key,
        create,
        comment):

    results_exec, results_pass, results_fail, results_skip = xunit.parse_results(path)

    folders = [part.strip()
               for part in (folder_name or '').split(',') if part.strip()]

    j = jira.Jira(jira_token)
    test_from_jira = j.get_all_tests_as_lut(
        fields="name,key", folder=folders or None)
    logging.info(
        f"Retrieved {len({test['key'] for test in test_from_jira.values()})} "
        f"tests from Jira ({len(test_from_jira)} lookup aliases)")
    assignees: dict = {}

    # if tests are not found in Jira, list them and raise an exception
    missing_tests = [tc_key for tc_key in results_exec + results_pass + results_fail + results_skip if tc_key not in test_from_jira]
    # if missing_tests:
    #     logging.error(f"Tests not found in Jira: {missing_tests}")
    #     #write not found tests in file for debugging
    #     with open('not_found.txt', 'w') as f:
    #         for test in missing_tests:
    #             f.write(f"{test}\n")
    #     raise jira.JiraException(f"Tests not found in Jira: {missing_tests}")

    # if missing tests are found, we can still upload the results for the tests that were found
    list_of_testcases_pass = [
        test_from_jira[tc_key]['key'] for tc_key in results_pass if tc_key in test_from_jira]
    list_of_testcases_fail = [
        test_from_jira[tc_key]['key'] for tc_key in results_fail if tc_key in test_from_jira]
    list_of_testcases_skip = [
        test_from_jira[tc_key]['key'] for tc_key in results_skip if tc_key in test_from_jira]

    logging.info(
        f"Uploading results to Jira: {len(list_of_testcases_pass)} passed, "
        f"{len(list_of_testcases_fail)} failed, "
        f"{len(list_of_testcases_skip)} skipped")
    # try:
    #     list_of_testcases_pass = [
    #         test_from_jira[tc_key]['key'] for tc_key in results_pass]
    #     list_of_testcases_fail = [
    #         test_from_jira[tc_key]['key'] for tc_key in results_fail]
    #     list_of_testcases_skip = [
    #         test_from_jira[tc_key]['key'] for tc_key in results_skip]
    # except KeyError as e:
    #     raise jira.JiraException(
    #         f'Test case with key "{
    #             e.args[0]}" not found in Jira')

    method = j.update_test_cycle_results
    method(
        folders[0] if folders else None,
        cycle_name,
        comment,
        assignees,
        list_of_testcases_pass,
        list_of_testcases_fail,
        list_of_testcases_skip,
        cycle_key=cycle_key)


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
                        help="Comma-separated Zephyr folders to look up test "
                             "cases in; subfolders must be listed explicitly",
                        default=None,
                        action='store')

    parser.add_argument('-C', '--cycle',
                        help="Cycle to upload results to",
                        default=None,
                        action='store')

    parser.add_argument(
        '--cycle-key',
        help="Cycle key (e.g. 'sc-R123'); if set, skips the folder/cycle name lookup",
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
        upload_zephyr_results(
            args.path,
            args.jira_token,
            args.folder,
            args.cycle,
            args.cycle_key,
            args.create,
            args.comment)
    except jira.JiraException as e:
        print()
        print(f"ERROR: {e}")
        print("Exiting due to Jira Exception")
        exit(1)


if __name__ == "__main__":
    main()
