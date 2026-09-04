# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging

import libraries.jira as jira
import libraries.versions as scenescape_versions

logging.basicConfig(level=logging.INFO)

def create_zephyr_cycle(jira_token, folder_name, version_name, cycle_name, test_cases_folder=None, add_tests=False, status=None, automated=None):
    """
    Creates a Zephyr test cycle based on specified parameters.
    It can add new tests to the cycle or create entirely new test cycles with a specified set of tests based on the folder and version provided.

    Parameters:
        jira_token (str): JIRA API token for authentication.
        folder_name (str): Folder under which the test cycle is to be created or updated.
        version_name (str): The name of the fixed version in JIRA under which the test cycle is to be managed.
        cycle_name (str): The name of the test cycle to create or update.
        test_cases_folder (str | None): Folder containing the test cases to be added to the cycle.
        status (list[str] | None): Test case statuses to include. All statuses when None.
        automated (bool | None): Restrict to automated or manual tests. Both when None.

    Returns:
        None; the function directly modifies the test cycles in JIRA based on the Zephyr API.
    """
    j = jira.Jira(jira_token)

    if not add_tests:
        j.create_test_cycle(folder_name, cycle_name, version_name)
    else:
        j.add_tests_to_cycle(folder_name, test_cases_folder, cycle_name, version_name,
                             status=status, automated=automated)
        logging.info(f"Added tests to cycle '{cycle_name}' in version '{version_name}'.")

def main():
    parser = argparse.ArgumentParser(
        description="Create or update a Zephyr test cycle in JIRA based on specified parameters."
    )
    parser.add_argument("--debug", 
                        action="store_true", 
                        help="Enable debug logging")

    parser.add_argument("--jira-token", 
                        required=True, 
                        help="JIRA API token for authentication")

    parser.add_argument("--folder", 
                        required=True, 
                        help="Folder under which the test cycle is to be created or updated")

    parser.add_argument("--test-cases-folder", 
                        required=True, 
                        help="Folder containing the test cases to be added to the cycle")

    parser.add_argument("--version", 
                        required=True, 
                        help="The name of the fixed version in JIRA under which the test cycle is to be managed")

    parser.add_argument("--cycle", 
                        help="The name of the test cycle to create or update")

    parser.add_argument("--add-tests", 
                        action="store_true", 
                        help="Whether to add tests from the folder to the newly created cycle")

    parser.add_argument("--status",
                        help="Comma separated test case statuses to include (e.g. Draft,Approved). All statuses if omitted")

    parser.add_argument("--automated", 
                        choices=["true", "false"],
                        help="Only include automated (true) or manual (false) tests. Both if omitted")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.version not in scenescape_versions.versions:
        raise ValueError(f"Invalid version: {args.version}. Must be one of: {', '.join(scenescape_versions.versions)}")

    create_zephyr_cycle(
        jira_token=args.jira_token,
        folder_name=args.folder,
        test_cases_folder=args.test_cases_folder,
        version_name=args.version,
        cycle_name=args.cycle,
        add_tests=args.add_tests,
        status=[part.strip() for part in args.status.split(',') if part.strip()] if args.status else None,
        automated=None if args.automated is None else args.automated == "true",
    )

if __name__ == "__main__":
    main()
