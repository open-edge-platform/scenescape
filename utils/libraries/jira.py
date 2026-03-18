"""
Enhanced Zephyr Scale API Integration

This module provides a comprehensive interface to Zephyr Scale (ATM) API with:
- Parallel test fetching for improved performance
- Automatic folder creation and error recovery
- User caching to reduce API calls
- Batched operations for scalability
- Enhanced error handling and logging

Environment Variables:
    JIRA_TEAM: Team name (default: Vision_AI)
    JIRA_PROJECT: Project key (default: ITEP)
    ZEPHYR_API_BASE: Zephyr Scale API base URL
    JIRA_API_BASE: JIRA REST API base URL
"""

import logging
import os
import requests
import urllib3
import concurrent.futures
from typing import Dict, List, Optional, Any

# import utils.libraries.test_categories_scale as test_categories
import libraries.test_categories as test_categories

logger = logging.getLogger(__name__)

# Disable SSL warnings
urllib3.disable_warnings()


class JiraException(Exception):
    """Enhanced exception with response details."""
    
    def __init__(self, message: str, response=None):
        if response is not None:
            try:
                error_data = response.json()
                if 'errorMessages' in error_data:
                    for m in error_data['errorMessages']:
                        message += f'\n  {m}'
                if 'errors' in error_data:
                    for field, err in error_data['errors'].items():
                        message += f'\n  {field}: {err}'
            except (ValueError, KeyError, TypeError) as e:
                logger.warning(f"Could not parse error response: {e}")
                # Try to include raw response text
                if hasattr(response, 'text'):
                    message += f'\n  Raw response: {response.text[:500]}'
        
        super().__init__(message)
        self.response = response


class Jira:
    """
    Zephyr Scale API Client
    
    Provides methods for managing test cases, test cycles, and test executions
    in Zephyr Scale (formerly Adaptavist Test Management).
    """
    
    # Configuration (can be overridden via environment variables)
    team = os.getenv('JIRA_TEAM', 'sc')
    project = os.getenv('JIRA_PROJECT', 'ITEP')

    def __init__(self, api_token: str, sandbox: bool = False):
        """
        Initialize Jira client.
        
        Args:
            api_token: JIRA personal access token
            sandbox: Whether to use sandbox environment (currently unused)
        """
        self.my_username = os.getenv('JIRA_USER')
        self._user_cache: Dict[str, Any] = {}

        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "content-type": "application/json"
        }

        # Use environment variables or defaults
        self.api_base = os.getenv(
            'ZEPHYR_API_BASE',
            'https://jira.devtools.st.com/rest/atm/1.0/'
        )
        self.jira_api_base = os.getenv(
            'JIRA_API_BASE',
            'https://jira.devtools.st.com/rest/api/2/'
        )
        
        logger.info(f"Initialized Jira client for team '{self.team}', project '{self.project}'")

    def get(self, url: str, params: Optional[Dict] = None) -> Any:
        """Execute GET request with error handling."""
        logger.debug(f'GET {url}')
        try:
            r = requests.get(url, params=params, headers=self.headers, verify=False, timeout=30)
            r.raise_for_status()
        except requests.exceptions.Timeout:
            raise JiraException(f'Request timed out: {url}')
        except requests.exceptions.HTTPError as e:
            logger.error(f'HTTP Error: {e}')
            logger.error(f'Response Status: {r.status_code}')
            logger.error(f'Response Text: {r.text[:500]}')
            raise JiraException(f'HTTPError {e}', response=e.response)
        except requests.exceptions.RequestException as e:
            raise JiraException(f'Request failed: {e}')
        
        logger.debug(f'Response status: {r.status_code}')
        
        try:
            return r.json()
        except ValueError as e:
            logger.error(f'Invalid JSON response: {e}')
            logger.error(f'Response text: {r.text[:1000]}')
            raise JiraException(f'Invalid JSON response: {e}')

    def post(self, url: str, json: Any) -> Any:
        """Execute POST request with error handling."""
        logger.debug(f'POST {url}')
        try:
            r = requests.post(url, headers=self.headers, verify=False, json=json, timeout=30)
            r.raise_for_status()
        except requests.exceptions.Timeout:
            raise JiraException(f'Request timed out: {url}')
        except requests.exceptions.HTTPError as e:
            logger.error(f'HTTP Error: {e}')
            logger.error(f'Response Status: {r.status_code}')
            logger.error(f'Response Text: {r.text[:500]}')
            raise JiraException(f'HTTPError {e}', response=e.response)
        except requests.exceptions.RequestException as e:
            raise JiraException(f'Request failed: {e}')
        
        logger.debug(f'Response status: {r.status_code}')
        
        try:
            return r.json()
        except ValueError as e:
            logger.error(f'Invalid JSON response: {e}')
            raise JiraException(f'Invalid JSON response: {e}')

    def put(self, url: str, json: Any) -> Any:
        """Execute PUT request with error handling."""
        logger.debug(f'PUT {url}')
        try:
            r = requests.put(url, headers=self.headers, verify=False, json=json, timeout=30)
            r.raise_for_status()
        except requests.exceptions.Timeout:
            raise JiraException(f'Request timed out: {url}')
        except requests.exceptions.HTTPError as e:
            logger.error(f'HTTP Error: {e}')
            logger.error(f'Response Status: {r.status_code}')
            logger.error(f'Response Text: {r.text[:500]}')
            raise JiraException(f'HTTPError {e}', response=e.response)
        except requests.exceptions.RequestException as e:
            raise JiraException(f'Request failed: {e}')
        
        logger.debug(f'Response status: {r.status_code}')
        
        # Empty response is valid for 200 OK
        if r.status_code == 200 and len(r.content) == 0:
            return {}
        
        try:
            return r.json()
        except ValueError as e:
            logger.error(f'Invalid JSON response: {e}')
            raise JiraException(f'Invalid JSON response: {e}')

    def delete(self, url: str) -> None:
        """Execute DELETE request with error handling."""
        logger.debug(f'DELETE {url}')
        try:
            r = requests.delete(url, headers=self.headers, verify=False, timeout=30)
            r.raise_for_status()
        except requests.exceptions.Timeout:
            raise JiraException(f'Request timed out: {url}')
        except requests.exceptions.HTTPError as e:
            logger.error(f'HTTP Error: {e}')
            raise JiraException(f'HTTPError {e}', response=e.response)
        except requests.exceptions.RequestException as e:
            raise JiraException(f'Request failed: {e}')
        
        logger.debug(f'DELETE successful: {r.status_code}')

    # @property
    # def key(self) -> str:
    #     """Get current user's username (cached)."""
    #     if self._key:
    #         return self._key

    #     r = self.get(self.jira_api_base + 'myself')
    #     self._key = r['key']
    #     logger.info(f"Current user: {self._key}")
    #     return self._key

    def get_username_from_userkey(self, user_key: str) -> str:
        """Get username from user key (cached)."""
        if user_key in self._user_cache:
            return self._user_cache[user_key]['name']

        r = self.get(self.jira_api_base + f'user?key={user_key}')
        self._user_cache[user_key] = r
        return self._user_cache[user_key]['name']

    def get_user_displayname_from_userkey(self, user_key: str) -> str:
        """Get user display name from user key (cached)."""
        if user_key in self._user_cache:
            return self._user_cache[user_key]['displayName']

        r = self.get(self.jira_api_base + f'user?key={user_key}')
        self._user_cache[user_key] = r
        return self._user_cache[user_key]['displayName']

    def fetch_issues(self, params: Dict, start_at: int, max_results: int) -> List[Dict]:
        """Fetch a single batch of issues."""
        local_params = params.copy()
        local_params['startAt'] = start_at
        logger.info(f"Fetching issues {start_at}-{start_at + max_results - 1}")
        logger.info(f"Query params: {local_params}")
        r = self.get(self.api_base + 'testcase/search', params=local_params)
        logger.debug(f"Retrieved {len(r)} issues")
        return r

    def fetch_batch_issues(self, params: Dict, start_at: int, batch_qty: int, max_results: int) -> List[Dict]:
        """
        Fetch multiple batches in parallel using ThreadPoolExecutor.
        
        Args:
            params: Query parameters
            start_at: Starting index
            batch_qty: Number of parallel batches
            max_results: Results per batch
            
        Returns:
            Combined results from all batches
        """
        logger.info(f'Starting parallel fetch from index {start_at} ({batch_qty} batches)')
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_qty) as executor:
            futures = [
                executor.submit(self.fetch_issues, params, start_at + i * max_results, max_results)
                for i in range(batch_qty)
            ]
            
            results = []
            for future in concurrent.futures.as_completed(futures):
                try:
                    data = future.result()
                    results.extend(data)
                except Exception as e:
                    logger.error(f"Failed to fetch batch: {e}")
                    raise
            
            return results

    def get_tests(self, query: str, fields: str = '') -> List[Dict]:
        """
        Get tests with parallel fetching and pagination.
        
        Note: Server enforces max_results limit. This method handles pagination
        automatically and uses parallel fetching for improved performance.
        
        Args:
            query: JQL query string
            fields: Comma-separated field names (optional, for performance)
            
        Returns:
            List of test case dictionaries
        """
        # Optimize batch size based on requested fields
        if fields == 'name,key':
            max_results = 1000  # Lightweight queries can fetch more
            batch_qty = 2
        else:
            max_results = 200   # Full data needs smaller batches
            batch_qty = 10

        issues = []
        logger.info(f"Getting tests from project '{self.project}'")

        params = {
            'query': query,
            'maxResults': max_results,
        }

        if fields:
            params['fields'] = fields

        while True:
            params['startAt'] = len(issues)
            new_issues = self.fetch_batch_issues(params, len(issues), batch_qty, max_results)

            issues.extend(new_issues)

            if len(new_issues) < max_results * batch_qty:
                break  # No more results

            logger.info(f"Progress: {len(issues)} tests retrieved")

        logger.info(f"Total: {len(issues)} tests retrieved")
        return issues

    def get_all_tests(self, fields: str = '') -> List[Dict]:
        """Get all tests for configured team and project."""
        query = f'projectKey = "{self.project}" AND "Team" IN ("{self.team}")'
        return self.get_tests(query, fields=fields)
    
    def get_tests_in_folder(self, folder: str, fields: str = '') -> List[Dict]:
        """
        Get tests in a specific folder (and all subfolders).
        
        Args:
            folder: Folder path (e.g., "/Vis/api" or "/Vis/api/auth")
            fields: Comma-separated field names (optional)
            
        Returns:
            List of test case dictionaries in the specified folder
            
        Example:
            >>> j.get_tests_in_folder("/Vis/api")
            # Returns all tests in /Vis/api and /Vis/api/* subfolders
        """
        # JQL query with name filter
        query = (f'projectKey = "{self.project}" AND '
            f'"Team" IN ("{self.team}") AND '
            f'name ~ "Vision_AI/API"')
        
        logger.info(f"Fetching tests in folder: {folder}")
        return self.get_tests(query, fields=fields)

    def get_all_tests_as_lut(self, fields: str = '') -> Dict[str, Dict]:
        """
        Get all tests as a lookup table.
        
        Returns:
            Dictionary mapping test ID (e.g., 'Vision_AI/SSCAPE/01') to test data
        """
        tests = self.get_all_tests(fields=fields)

        lut_tests = {}
        for t in tests:
            ss_key = t['name'].split(':', 1)[0]
            lut_tests[ss_key] = t

        logger.info(f"Created lookup table with {len(lut_tests)} tests")
        return lut_tests

    def get_all_defects(self) -> List[Dict]:
        """Get all defects/bugs for configured project."""
        max_results = 1000
        issues = []

        logger.info("Getting all defects in project")

        while True:
            start_at = len(issues)
            r = self.get(
                self.jira_api_base +
                f'search?jql=project="{self.project}" '
                'AND (type="Bug" or type="Risk" or type="Task")'
                f'&fields=summary'
                f'&maxResults={max_results}&startAt={start_at}'
            )
            new_issues = r['issues']
            issues.extend(new_issues)

            if len(new_issues) < max_results:
                break

        logger.info(f"Retrieved {len(issues)} defects")
        return issues

    def get_all_defects_as_lut(self) -> Dict[str, Dict]:
        """Get all defects as lookup table keyed by issue key."""
        issues = self.get_all_defects()
        return {i['key']: i for i in issues}

    @staticmethod
    def summary_to_test_case_labels(summary: str) -> List[str]:
        """Extract hierarchical labels from test case summary."""
        ss_test_id = summary.split(':', 1)[0]
        parts = ss_test_id.split('/')
        labels = []
        for i in range(1, len(parts) - 1):
            labels.append('/'.join(parts[:i + 1]))
        return labels

    @staticmethod
    def summary_to_test_case_id(summary: str) -> str:
        """Extract test case ID from summary."""
        return summary.split(':', 1)[0]

    # Test Case Management

    def create_test_case_folder(self, folder_name: str) -> None:
        """Create a test case folder."""
        data = {
            "projectKey": self.project,
            "name": folder_name,
            "type": "TEST_CASE"
        }
        
        logger.info(f"Creating test case folder: {folder_name}")
        self.post(self.api_base + 'folder', data)

    def add_test_case(
        self,
        summary: str,
        folder: str,
        description: str,
        versions: str,
        requirements: Optional[List[str]] = None,
        priority: Optional[str] = None,
        owner: Optional[str] = None,
        automated: bool = False,
        status: str = "Approved",
    ) -> Dict:
        """
        Create a new test case in Zephyr Scale.
        
        Args:
            summary: Test case name/summary
            folder: Folder path
            description: Test description (HTML supported)
            versions: Comma-separated version list
            requirements: List of linked requirement keys
            priority: Test priority
            owner: Owner user key (defaults to current user)
            automated: Whether test is automated
            status: Test status (Approved, Draft, Deprecated)
        Returns:
            Created test case data
        """
        test_case_id = Jira.summary_to_test_case_id(summary)
        labels = Jira.summary_to_test_case_labels(summary)
        test_category, test_type, test_component = test_categories.summary_to_test_category(summary)

        labels = labels + [test_category, test_type]
        if automated:
            labels.append('Automated')

        # Replace spaces in labels (Zephyr Scale requirement)
        labels = [label.replace(' ', '_') for label in labels]

        # Build customFields, excluding None values to avoid 500 errors
        custom_fields = {
            "ID": test_case_id,
            "Test Category": test_category,
            "Test Type": test_type,
            "Automated": automated,
            "Team": self.team,
        }
        
        # Only add Affected Versions if not empty
        if versions:
            custom_fields["Affected Versions"] = versions
        
        test_data = {
            "projectKey": self.project,
            "name": summary,
            "labels": labels,
            "owner": owner if owner is not None else self.my_username,
            "component": test_component,
            "customFields": custom_fields,
            "objective": description,
            "folder": folder,
            "status": status
        }

        if requirements:
            test_data['issueLinks'] = requirements

        if priority:
            test_data["priority"] = priority

        try:
            logger.info(f"Creating test case: {summary}")
            r = self.post(self.api_base + 'testcase', test_data)
            logger.info(f"Created test case: {r.get('key', 'unknown')}")
            return r
        except JiraException as e:
            # Auto-create folder if it doesn't exist
            if (e.response and e.response.status_code == 400 and
                    'errorMessages' in e.response.json() and
                    any('was not found for field folder' in s 
                        for s in e.response.json()['errorMessages'])):
                
                logger.info(f"Folder '{folder}' not found, creating it")
                self.create_test_case_folder(folder)
                r = self.post(self.api_base + 'testcase', test_data)
                logger.info(f"Created test case: {r.get('key', 'unknown')}")
                return r
            else:
                raise

    def update_test_case(self, test_case_key: str, data: Dict) -> None:
        """
        Update an existing test case.
        
        Args:
            test_case_key: Test case key (e.g., 'NEX-T12345')
            data: Update data dictionary
        """
        try:
            logger.info(f"Updating test case: {test_case_key}")
            self.put(self.api_base + f'testcase/{test_case_key}', data)
            logger.info(f"Updated test case: {test_case_key}")
        except JiraException as e:
            # Auto-create folder if specified but doesn't exist
            if (e.response and e.response.status_code == 400 and
                    'folder' in data and
                    'errorMessages' in e.response.json() and
                    any('was not found for field folder' in s
                        for s in e.response.json()['errorMessages'])):
                
                logger.info(f"Folder '{data['folder']}' not found, creating it")
                self.create_test_case_folder(data['folder'])
                self.put(self.api_base + f'testcase/{test_case_key}', data)
                logger.info(f"Updated test case: {test_case_key}")
            else:
                raise

    # Test Cycle Management

    def get_test_cycle(self, cycle_key: str) -> Dict:
        """Get test cycle/run details."""
        logger.info(f"Fetching test cycle: {cycle_key}")
        return self.get(self.api_base + f'testrun/{cycle_key}')

    def create_test_cycle_folder(self, folder_name: str) -> None:
        """Create a test run folder."""
        data = {
            "projectKey": self.project,
            "name": folder_name,
            "type": "TEST_RUN"
        }

        try:
            logger.info(f"Creating test run folder: {folder_name}")
            self.post(self.api_base + 'folder', data)
        except JiraException as e:
            # Folder might already exist
            if (e.response and e.response.status_code == 400 and
                    'errorMessages' in e.response.json() and
                    any('already exists' in s for s in e.response.json()['errorMessages'])):
                logger.info(f"Folder '{folder_name}' already exists")
            else:
                logger.error(e.response.json() if e.response else str(e))
                raise

    def create_test_cycle(self, folder_name: str, cycle_name: str, version: str) -> str:
        """
        Create a test cycle/run.
        
        Note: Test cases are added separately via create_test_cycle_results()
        
        Args:
            folder_name: Folder to create cycle in
            cycle_name: Name of the cycle
            version: Version string
            
        Returns:
            Cycle key (e.g., 'sc-R123')
        """
        data = {
            "name": cycle_name,
            "projectKey": self.project,
            "version": version,
            "customFields": {
                "Team": self.team,
            },
            'folder': folder_name
        }

        try:
            logger.info(f"Creating test cycle: {cycle_name}")
            r = self.post(self.api_base + 'testrun', data)
            cycle_key = r['key']
            logger.info(f"Created test cycle: {cycle_key}")
            return cycle_key
        except JiraException as e:
            # Auto-create folder if it doesn't exist
            if (e.response and e.response.status_code == 400 and
                    'errorMessages' in e.response.json() and
                    any('was not found for field folder' in s
                        for s in e.response.json()['errorMessages'])):
                
                logger.info(f"Folder '{folder_name}' not found, creating it")
                self.create_test_cycle_folder(folder_name)
                r = self.post(self.api_base + 'testrun', data)
                cycle_key = r['key']
                logger.info(f"Created test cycle: {cycle_key}")
                return cycle_key
            else:
                raise

    def get_cycle_from_folder(self, folder_name: str, cycle_name: str) -> str:
        """Find cycle key by folder and name."""
        params = {
            'query': f'projectKey = "{self.project}" AND folder = "{folder_name}"',
            'fields': 'key,name'
        }
        
        logger.info(f"Searching for cycle '{cycle_name}' in folder '{folder_name}'")
        cycles = self.get(self.api_base + 'testrun/search', params)
        
        for c in cycles:
            if c['name'] == cycle_name:
                logger.info(f"Found cycle: {c['key']}")
                return c['key']
        
        raise JiraException(f'Cycle "{cycle_name}" not found in folder "{folder_name}"')

    def create_test_cycle_results(
        self,
        folder_name: str,
        cycle_name: str,
        comment: str,
        assignees: Dict[str, str],
        testcases_pass: List[str],
        testcases_fail: List[str],
        testcases_unexecuted: List[str]
    ) -> None:
        """
        Create test results in a cycle (batch upload).
        
        Args:
            folder_name: Test run folder name
            cycle_name: Test run name
            comment: Comment for all results
            assignees: Dict mapping test keys to assignee keys
            testcases_pass: List of passing test keys
            testcases_fail: List of failing test keys
            testcases_unexecuted: List of unexecuted test keys
        """
        cycle_key = self.get_cycle_from_folder(folder_name, cycle_name)

        # Build result data
        data = (
            [{'status': 'Pass', 'testCaseKey': t,
              'assignedTo': assignees[t], 'executedBy': self.my_username}
             for t in testcases_pass] +
            [{'status': 'Fail', 'testCaseKey': t,
              'assignedTo': assignees[t], 'executedBy': self.my_username}
             for t in testcases_fail] +
            [{'status': 'Not Executed', 'testCaseKey': t,
              'assignedTo': assignees[t]}
             for t in testcases_unexecuted]
        )

        if comment:
            for d in data:
                d['comment'] = comment

        # Batch upload with progress tracking
        upload_limit = 50
        max_workers = 10

        logger.info(f"Creating {len(data)} test executions in cycle {cycle_key}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for chunk_start in range(0, len(data), upload_limit):
                chunk_end = min(chunk_start + upload_limit, len(data))
                chunk = data[chunk_start:chunk_end]
                future = executor.submit(
                    self.post,
                    self.api_base + f'testrun/{cycle_key}/testresults',
                    chunk
                )
                futures[future] = (chunk_start, chunk_end)

            for future in concurrent.futures.as_completed(futures):
                chunk_start, chunk_end = futures[future]
                try:
                    _ = future.result()  # Check for exceptions
                    logger.info(f"Uploaded results {chunk_start + 1}-{chunk_end}")
                except Exception as e:
                    logger.error(f"Failed to upload chunk {chunk_start}-{chunk_end}: {e}")
                    raise

        logger.info(f"Successfully uploaded all {len(data)} test results")

    def update_test_cycle_results(
        self,
        folder_name: str,
        cycle_name: str,
        comment: str,
        assignees: Dict[str, str],
        testcases_pass: List[str],
        testcases_fail: List[str],
        testcases_unexecuted: List[str]
    ) -> None:
        """
        Update test results in a cycle (individual updates with auto-add).
        
        This method attempts to update existing test results, and automatically
        adds tests to the cycle if they don't exist yet.
        
        Args:
            folder_name: Test run folder name
            cycle_name: Test run name
            comment: Comment for all results
            assignees: Dict mapping test keys to assignee keys
            testcases_pass: List of passing test keys
            testcases_fail: List of failing test keys
            testcases_unexecuted: List of unexecuted test keys
        """
        cycle_key = self.get_cycle_from_folder(folder_name, cycle_name)

        # Combine all test cases with their statuses
        data = {t: 'Pass' for t in testcases_pass}
        data.update({t: 'Fail' for t in testcases_fail})
        data.update({t: 'Not Executed' for t in testcases_unexecuted})

        logger.info(f"Updating {len(data)} test results in cycle {cycle_key}")

        for i, (key, status) in enumerate(data.items(), start=1):
            result = {
                'status': status,
                'executedBy': self.my_username,
                'assignedTo': assignees[key],
                'comment': comment
            }
            
            try:
                # Try to update existing result
                self.put(
                    self.api_base + f'testrun/{cycle_key}/testcase/{key}/testresult',
                    result
                )
            except JiraException as e:
                # If test not in cycle, add it
                if (e.response and e.response.status_code == 400 and
                        'errorMessages' in e.response.json() and
                        any('No test execution found on test run' in s
                            for s in e.response.json()['errorMessages'])):
                    
                    logger.debug(f"Test {key} not in cycle, adding it")
                    self.post(
                        self.api_base + f'testrun/{cycle_key}/testcase/{key}/testresult',
                        result
                    )
                else:
                    raise
            
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{len(data)} results updated")

        logger.info(f"Successfully updated all {len(data)} test results")

    def update_test_cycle_results(self, folder_name, cycle_name, comment, assignees,
                                  testcases_pass, testcases_fail, testcases_unexecuted):
        # attempt first to PUT to the existing test results and if this does not exist create it

        cycle_key = self.get_cycle_from_folder(folder_name, cycle_name)

        data = {t: 'Pass' for t in testcases_pass}
        data.update({t: 'Fail' for t in testcases_fail})
        data.update({t: 'Not Executed' for t in testcases_unexecuted})

        logger.info(f"Upload {len(data)} tests to cycle")

        for i, (key, status) in enumerate(data.items(), start=1):
            # Handle assignees as either dict or set/list
            assignee = assignees.get(key, self.my_username) if isinstance(assignees, dict) else self.my_username
            result = {'status': status,
                      'executedBy': self.my_username,
                      'assignedTo': assignee,
                      'comment': comment}
            try:
                self.put(self.api_base + f'testrun/{cycle_key}/testcase/{key}/testresult', result)
            except JiraException as e:
                # if the PUT fails with this message it is due to test case not being in the cycle
                # so run the same command but with POST to add it
                # TODO: we could do better with a GET of all test cases in the cycle
                #   and check if the test case is in there first (this will use less API calls)
                if e.response.status_code == 400 and \
                        'errorMessages' in e.response.json() and \
                        any('No test execution found on test run' in s for s in e.response.json()['errorMessages']):
                    self.post(self.api_base + f'testrun/{cycle_key}/testcase/{key}/testresult', result)
                else:
                    raise
            if i % 10 == 0:
                logger.info(f"... {i}")
