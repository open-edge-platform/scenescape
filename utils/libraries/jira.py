# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0


import concurrent.futures
import logging
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Union

import requests
import urllib3

logger = logging.getLogger(__name__)

urllib3.disable_warnings()

KEY_RE = re.compile(r'([A-Z]+-\d+)')
PAGE_SIZE = 100


class JiraException(Exception):
    """Exception that includes Jira error details when available."""

    def __init__(self, message: str, response=None):
        if response is not None:
            try:
                error_data = response.json()
                if 'errorMessages' in error_data:
                    for error_message in error_data['errorMessages']:
                        message += f'\n  {error_message}'
                if 'errors' in error_data:
                    for field, error in error_data['errors'].items():
                        message += f'\n  {field}: {error}'
            except (ValueError, KeyError, TypeError) as exc:
                logger.warning(f'Could not parse error response: {exc}')
                if hasattr(response, 'text'):
                    message += f'\n  Raw response: {response.text[:500]}'

        super().__init__(message)
        self.response = response


class Jira:
    """Small Jira ATM client focused on test result upload."""

    team = os.getenv('JIRA_TEAM')
    project = os.getenv('JIRA_PROJECT')

    def __init__(self, api_token: str, sandbox: bool = False):
        self._user_cache: Dict[str, Any] = {}
        self.my_username = os.getenv('JIRA_USER')
        self.headers = {
            'Authorization': f'Bearer {api_token}',
            'content-type': 'application/json',
        }
        self.api_base = os.getenv('ZEPHYR_API_BASE')
        self.jira_api_base = os.getenv('JIRA_API_BASE')
        logger.info(
            f"Initialized Jira client for team '{
                self.team}', project '{
                self.project}'")

    def get(self, url: str, params: Optional[Dict] = None) -> Any:
        logger.debug(f'GET {url}')
        try:
            response = requests.get(
                url,
                params=params,
                headers=self.headers,
                verify=False,
                timeout=30)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise JiraException(f'Request timed out: {url}')
        except requests.exceptions.HTTPError as exc:
            logger.error(f'HTTP Error: {exc}')
            logger.error(f'Response Status: {response.status_code}')
            logger.error(f'Response Text: {response.text[:500]}')
            raise JiraException(f'HTTPError {exc}', response=exc.response)
        except requests.exceptions.RequestException as exc:
            raise JiraException(f'Request failed: {exc}')

        try:
            return response.json()
        except ValueError as exc:
            logger.error(f'Invalid JSON response: {exc}')
            logger.error(f'Response text: {response.text[:1000]}')
            raise JiraException(f'Invalid JSON response: {exc}')

    def post(self, url: str, json: Any) -> Any:
        logger.debug(f'POST {url}')
        try:
            response = requests.post(
                url,
                headers=self.headers,
                verify=False,
                json=json,
                timeout=30)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise JiraException(f'Request timed out: {url}')
        except requests.exceptions.HTTPError as exc:
            logger.error(f'HTTP Error: {exc}')
            logger.error(f'Response Status: {response.status_code}')
            logger.error(f'Response Text: {response.text[:500]}')
            raise JiraException(f'HTTPError {exc}', response=exc.response)
        except requests.exceptions.RequestException as exc:
            raise JiraException(f'Request failed: {exc}')

        try:
            return response.json()
        except ValueError as exc:
            logger.error(f'Invalid JSON response: {exc}')
            raise JiraException(f'Invalid JSON response: {exc}')

    def put(self, url: str, json: Any) -> Any:
        logger.debug(f'PUT {url}')
        try:
            response = requests.put(
                url,
                headers=self.headers,
                verify=False,
                json=json,
                timeout=30)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise JiraException(f'Request timed out: {url}')
        except requests.exceptions.HTTPError as exc:
            logger.error(f'HTTP Error: {exc}')
            logger.error(f'Response Status: {response.status_code}')
            logger.error(f'Response Text: {response.text[:500]}')
            raise JiraException(f'HTTPError {exc}', response=exc.response)
        except requests.exceptions.RequestException as exc:
            raise JiraException(f'Request failed: {exc}')

        if response.status_code == 200 and len(response.content) == 0:
            return {}

        try:
            return response.json()
        except ValueError as exc:
            logger.error(f'Invalid JSON response: {exc}')
            raise JiraException(f'Invalid JSON response: {exc}')

    def fetch_issues(
            self,
            params: Dict,
            start_at: int,
            max_results: int) -> List[Dict]:
        local_params = params.copy()
        local_params['startAt'] = start_at
        local_params['maxResults'] = max_results
        logger.info(f'Fetching issues {start_at}-{start_at + max_results - 1}')
        logger.info(f'Query params: {local_params}')
        response = self.get(
            self.api_base +
            'testcase/search',
            params=local_params)
        logger.debug(f'Retrieved {len(response)} issues')
        return response

    def fetch_batch_issues(
            self,
            params: Dict,
            start_at: int,
            batch_qty: int,
            max_results: int) -> List[Dict]:
        logger.info(f'Starting parallel fetch from index {
                    start_at} ({batch_qty} batches)')

        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_qty) as executor:
            futures = [
                executor.submit(
                    self.fetch_issues,
                    params,
                    start_at + i * max_results,
                    max_results) for i in range(batch_qty)]

            results = []
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.extend(future.result())
                except Exception as exc:
                    logger.error(f'Failed to fetch batch: {exc}')
                    raise

            return results

    def get_tests(self, query: str, fields: str = '',
                  page_size: int = PAGE_SIZE) -> List[Dict]:
        params = {
            'query': query,
            'fields': fields,
        }
        all_tests: List[Dict] = []
        start_at = 0
        while True:
            batch = self.fetch_issues(params, start_at, page_size)
            if not batch:
                break
            all_tests.extend(batch)
            start_at += len(batch)
            logger.info(
                f'Fetched {len(batch)} tests, total so far: {len(all_tests)}')
        return all_tests

    def get_all_tests(self, fields: str = '') -> List[Dict]:
        query = f'projectKey = "{self.project}" AND "Team" IN ("{self.team}")'
        return self.get_tests(query, fields=fields)

    def get_tests_in_folder(self,
            folder: Union[str, Iterable[str]],
            fields: str = '') -> List[Dict]:
        folders = [folder] if isinstance(folder, str) else list(folder)
        paths = []
        for entry in folders:
            path = '/' + entry.strip().strip('/')
            if '"' in path:
                raise JiraException(f'Invalid folder path: {entry}')
            paths.append(path)
        if not paths:
            raise JiraException('No folder specified')

        # Zephyr ATM matches folders exactly, so subfolders must be listed too.
        tests: List[Dict] = []
        seen = set()
        for path in paths:
            query = f'projectKey = "{self.project}" AND folder = "{path}"'
            logger.info(f'Fetching tests in folder: {path}')
            for test in self.get_tests(query, fields=fields):
                key = test.get('key')
                if key is not None and key in seen:
                    continue
                seen.add(key)
                tests.append(test)
        return tests

    def get_all_tests_as_lut(
            self,
            fields: str = '',
            folder: Optional[Union[str, Iterable[str]]] = None) -> Dict[str, Dict]:
        tests = self.get_tests_in_folder(
            folder, fields=fields) if folder else self.get_all_tests(
            fields=fields)
        

        lut_tests: Dict[str, Dict] = {}
        for test in tests:
            name = test.get('name', '') or ''
            if 'key' in test:
                lut_tests[test['key']] = test
            match = KEY_RE.search(name)
            if match:
                lut_tests[match.group(1)] = test
            short = name.split(':', 1)[0].strip()
            if short:
                lut_tests[short] = test
        return lut_tests

    def get_cycle_from_folder(self, folder_name: str, cycle_name: str) -> str:
        params = {
            'query': f'projectKey = "{
                self.project}" AND folder = "{folder_name}"',
            'fields': 'key,name',
        }

        logger.info(f"Searching for cycle '{
                    cycle_name}' in folder '{folder_name}'")
        cycles = self.get(self.api_base + 'testrun/search', params)
        logger.info(f"Cycles found in folder '{folder_name}': {
                    [cycle['name'] for cycle in cycles]}")

        for cycle in cycles:
            if cycle['name'] == cycle_name:
                logger.info(f"Found cycle: {cycle['key']}")
                return cycle['key']

        raise JiraException(
            f'Cycle "{cycle_name}" not found in folder "{folder_name}"')

    def update_test_cycle_results(
        self,
        folder_name: str,
        cycle_name: str,
        comment: str,
        assignees: Dict[str, str],
        testcases_pass: List[str],
        testcases_fail: List[str],
        testcases_unexecuted: List[str],
        cycle_key: Optional[str] = None,
    ) -> None:
        cycle_key = cycle_key or self.get_cycle_from_folder(
            folder_name, cycle_name)

        data = {test_key: 'Pass' for test_key in testcases_pass}
        data.update({test_key: 'Fail' for test_key in testcases_fail})
        data.update(
            {test_key: 'Not Executed' for test_key in testcases_unexecuted})

        logger.info(f'Updating {len(data)} test results in cycle {cycle_key}')

        for index, (key, status) in enumerate(data.items(), start=1):
            result = {
                'status': status,
                'executedBy': self.my_username,
                'assignedTo': assignees.get(key, self.my_username),
                'comment': comment,
            }

            try:
                self.put(
                    self.api_base +
                    f'testrun/{cycle_key}/testcase/{key}/testresult',
                    result)
            except JiraException as exc:
                if (exc.response and exc.response.status_code == 400 and 'errorMessages' in exc.response.json() and any(
                        'No test execution found on test run' in message for message in exc.response.json()['errorMessages'])):
                    logger.debug(f'Test {key} not in cycle, adding it')
                    self.post(
                        self.api_base +
                        f'testrun/{cycle_key}/testcase/{key}/testresult',
                        result)
                else:
                    raise

            if index % 10 == 0:
                logger.info(f'Progress: {index}/{len(data)} results updated')

        logger.info(f'Successfully updated all {len(data)} test results')
