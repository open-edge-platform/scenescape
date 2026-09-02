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
RESULT_BATCH_SIZE = 50


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
    """Jira ATM client focused on test result upload."""

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
            fields: str = '',
            status: Optional[Union[str, Iterable[str]]] = None,
            automated: Optional[bool] = None) -> List[Dict]:
        folders = [folder] if isinstance(folder, str) else list(folder)
        paths = []
        for entry in folders:
            path = '/' + entry.strip().strip('/')
            if '"' in path:
                raise JiraException(f'Invalid folder path: {entry}')
            paths.append(path)
        if not paths:
            raise JiraException('No folder specified')

        wanted_status = None
        if status is not None:
            values = [status] if isinstance(status, str) else list(status)
            wanted_status = {value.strip().lower()
                             for value in values if value and value.strip()} or None

        # Filters are applied client side, so the fields they rely on must be fetched.
        if fields:
            requested = [field.strip()
                         for field in fields.split(',') if field.strip()]
            if wanted_status and 'status' not in requested:
                requested.append('status')
            if automated is not None:
                for field in ('customFields', 'labels'):
                    if field not in requested:
                        requested.append(field)
            fields = ','.join(requested)

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
                if wanted_status and (
                        test.get('status') or '').strip().lower() not in wanted_status:
                    continue
                if automated is not None and self.is_automated(test) is not automated:
                    continue
                seen.add(key)
                tests.append(test)
        if wanted_status or automated is not None:
            logger.info(f'Kept {len(tests)} tests after filtering '
                        f'(status={sorted(wanted_status) if wanted_status else "any"}, '
                        f'automated={automated if automated is not None else "any"})')
        return tests

    def current_user_key(self) -> Optional[str]:
        """Zephyr records the executor by Jira user key, so fall back to the token owner."""
        if self.my_username:
            return self.my_username
        if not self.jira_api_base:
            logger.warning('JIRA_USER and JIRA_API_BASE unset; results will have no executor')
            return None
        try:
            myself = self.get(self.jira_api_base + 'myself')
        except JiraException as exc:
            logger.warning(f'Could not resolve the current Jira user: {exc}')
            return None
        self.my_username = myself.get('key') or myself.get('name')
        logger.info(f'Resolved executing Jira user: {self.my_username}')
        return self.my_username

    TRUTHY = {'true', 'yes', 'y', '1', 'automated'}

    @classmethod
    def is_automated(cls, test: Dict) -> bool:
        """Zephyr has no automation flag, so use the 'Automated' custom field or label."""
        value = (test.get('customFields') or {}).get('Automated')
        if isinstance(value, bool):
            return value
        if value is not None:
            return str(value).strip().lower() in cls.TRUTHY
        labels = {str(label).strip().lower()
                  for label in test.get('labels') or []}
        return 'automated' in labels

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

    def create_test_cycle(self, folder_name: str, cycle_name: Optional[str] = None,
                          version: str | None = None,
                          test_keys: Optional[Iterable[str]] = None) -> str:
        if not cycle_name:
            from datetime import datetime
            cycle_name = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        data = {
            "name": cycle_name,
            "projectKey": self.project,
            "version": version,
            "customFields": {
                "Team": self.team,
            },
            'folder': folder_name
        }
        # ATM 1.0 only accepts test cases through the test run 'items' array.
        if test_keys:
            data['items'] = [{'testCaseKey': key} for key in test_keys]
        logger.info(f'Creating new test cycle "{cycle_name}" in folder "{folder_name}"')
        try:
            response = self.post(self.api_base + 'testrun', data)
            logger.info(f'Created test cycle with key: {response.get("key")}')
        except JiraException as exc:
            logger.error(f'Failed to create test cycle "{cycle_name}" in folder "{folder_name}": {exc}')
            raise

        return response.get('key')
        
    def add_tests_to_cycle(self, folder_name: str, test_cases_folder_name, cycle_name: str,
                           version: str | None = None,
                           status: Optional[Union[str, Iterable[str]]] = None,
                           automated: Optional[bool] = None) -> str:
        tests = self.get_tests_in_folder(
            test_cases_folder_name,
            fields='key',
            status=status,
            automated=automated)
        test_keys = [test['key'] for test in tests if test.get('key')]
        logger.info(f'Adding {len(test_keys)} tests to cycle "{cycle_name}" in folder "{folder_name}"')
        cycle_key = self.create_test_cycle(folder_name, cycle_name, version, test_keys=test_keys)
        logger.info(f'Cycle {cycle_key} created with {len(test_keys)} tests')
        return cycle_key
    

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
        if not cycle_key:
            raise JiraException(
                f'No cycle key provided for cycle "{cycle_name}" in folder "{folder_name}"')

        data = {test_key: 'Pass' for test_key in testcases_pass}
        data.update({test_key: 'Fail' for test_key in testcases_fail})
        data.update(
            {test_key: 'Not Executed' for test_key in testcases_unexecuted})

        logger.info(f'Updating {len(data)} test results in cycle {cycle_key}')

        executed_by = self.current_user_key()
        results = []
        for key, status in data.items():
            result = {
                'testCaseKey': key,
                'status': status,
            }
            if executed_by:
                result['executedBy'] = executed_by
                result['userKey'] = executed_by
            assigned_to = assignees.get(key, executed_by)
            if assigned_to:
                result['assignedTo'] = assigned_to
            if comment:
                result['comment'] = comment
            results.append(result)

        # The bulk endpoint also creates executions for test cases that are not
        # yet on the run; the per-test endpoints reject those with a 400.
        url = self.api_base + f'testrun/{cycle_key}/testresults'
        for start in range(0, len(results), RESULT_BATCH_SIZE):
            batch = results[start:start + RESULT_BATCH_SIZE]
            self.post(url, batch)
            logger.info(
                f'Progress: {start + len(batch)}/{len(results)} results uploaded')

        logger.info(f'Successfully updated all {len(results)} test results')
