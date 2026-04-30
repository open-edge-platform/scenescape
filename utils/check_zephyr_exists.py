"""
Enhanced Zephyr Scale Test Synchronization Script

Synchronizes markdown test documentation with Zephyr Scale test management system.

Features:
- Create missing test cases
- Update existing test fields
- Detect test renumbering
- Validate test metadata
- Progress tracking and logging

Usage:
    # Check existence
    python check_zephyr_exists.py --jira-token TOKEN path/to/tests

    # Create missing tests
    python check_zephyr_exists.py --jira-token TOKEN --create path/to/tests

    # Update fields
    python check_zephyr_exists.py --jira-token TOKEN --check-fields --update path/to/tests

Environment Variables:
    REPO_BASE_URL: GitHub repository base URL
    TEST_DOCS_DIR: Test documentation directory name
    REPO_BRANCH: Git branch name
    JIRA_TEAM: Team name
    JIRA_PROJECT: Project key
"""

import argparse
import logging
import os
import sys
from collections import defaultdict
from typing import List, Dict, Tuple, Optional, Any
from difflib import SequenceMatcher

# import utils.libraries.jira as jira
# import utils.libraries.markdown as md
# import utils.libraries.test_categories as test_categories

import libraries.jira as jira
import libraries.markdown as md
import libraries.test_categories as test_categories

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Configuration from environment variables
REPO_BASE_URL = os.getenv('REPO_BASE_URL')
TEST_DOCS_DIR = os.getenv('TEST_DOCS_DIR', 'test_plans')
REPO_BRANCH = os.getenv('REPO_BRANCH', 'main')

# Smart matching configuration
SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', '0.5'))
AUTO_UPDATE_THRESHOLD = float(os.getenv('AUTO_UPDATE_THRESHOLD', '0.95'))


def extract_url_from_html(html: str) -> Optional[str]:
    """Extract URL from HTML anchor tag in description."""
    if not html:
        return None
    import re
    match = re.search(r'href="([^"]+)"', html)
    return match.group(1) if match else None


def normalize_path(path: str) -> str:
    """Normalize file path for comparison."""
    path = path.replace('\\', '/')
    for prefix in ['../', './', 'test_plans/', '/test_plans/']:
        if path.startswith(prefix):
            path = path[len(prefix):]
    return path.lower()


def file_path_from_url(url: str) -> str:
    """Extract file path from GitHub URL."""
    if not url:
        return ''
    # Extract path after /blob/branch/
    if '/blob/' in url:
        parts = url.split('/blob/')
        if len(parts) > 1:
            # Get everything after branch name
            path_parts = parts[1].split('/', 1)
            if len(path_parts) > 1:
                return path_parts[1]
    return url


def find_test_matches(
        test_md, tests_jira: List[Dict]) -> List[Tuple[Dict, float, str, str]]:
    """
    Find potential matches for a markdown test in Jira.

    Returns list of tuples: (jira_test, confidence, reason, match_type)
    """
    matches = []

    # Parse markdown test info
    try:
        md_id, md_summary = test_md.title.split(':', 1)
        md_summary = md_summary.strip()
        md_parts = md_id.split('/')
        md_category = '/'.join(md_parts[:-1]) if len(md_parts) > 1 else ''
        md_number = md_parts[-1] if md_parts else ''
    except ValueError:
        return matches

    md_file_path = normalize_path(test_md.path)

    for jira_test in tests_jira:
        jira_title = jira_test.get('name', '')
        if not jira_title or ':' not in jira_title:
            continue

        try:
            jira_id, jira_summary = jira_title.split(':', 1)
            jira_summary = jira_summary.strip()
            jira_parts = jira_id.split('/')
            jira_category = '/'.join(jira_parts[:-1]
                                     ) if len(jira_parts) > 1 else ''
            jira_number = jira_parts[-1] if jira_parts else ''
        except ValueError:
            continue

        # Level 1: Exact title match (100%)
        if test_md.title == jira_title:
            matches.append((jira_test, 1.0, "Exact title match", "exact"))
            break

        # Level 2: Same file path (100%)
        # jira_objective = jira_test.get('objective', '')
        # if jira_objective:
        #     jira_url = extract_url_from_html(jira_objective)
        #     if jira_url:
        #         jira_file_path = normalize_path(file_path_from_url(jira_url))
        #         if jira_file_path and md_file_path == jira_file_path:
        #             matches.append((jira_test, 1.0, f"Same file path: {test_md.path}", "file_path"))
        #             continue

        # Level 3: Same category/summary, different number (90%)
        if md_category == jira_category and md_summary == jira_summary and md_number != jira_number:
            matches.append((jira_test, 0.9, f"Test ID changed: {
                           jira_number} → {md_number}", "id_change"))
            continue

        # Level 4: Same category, fuzzy summary (60-80%)
        if md_category == jira_category:
            similarity = SequenceMatcher(
                None, md_summary.lower(), jira_summary.lower()).ratio()
            if similarity >= SIMILARITY_THRESHOLD:
                confidence = similarity * 0.8
                matches.append(
                    (jira_test,
                     confidence,
                     f"Similar summary in same category ({
                         similarity:.0%} match)",
                        "fuzzy_same_cat"))
                continue

        # Level 5: Different category, very similar summary (60%)
        similarity = SequenceMatcher(
            None, md_summary.lower(), jira_summary.lower()).ratio()
        if similarity >= 0.85:
            confidence = similarity * 0.6
            matches.append(
                (jira_test,
                 confidence,
                 f"Similar summary, different category ({
                     similarity:.0%} match)",
                    "fuzzy_diff_cat"))

    # Sort by confidence (highest first)
    matches.sort(key=lambda m: (-m[1],
                                ['exact',
                                 'file_path',
                                 'id_change',
                                 'fuzzy_same_cat',
                                 'fuzzy_diff_cat'].index(m[3])))

    return matches


def path_to_url(path: str) -> str:
    """
    Convert local file path to GitHub URL.

    Args:
        path: Local file path

    Returns:
        GitHub URL to the file

    Example:
        >>> path_to_url('/home/user/project/test_plans/api/test.md')
        'https://github.com/org/repo/blob/main/test_plans/api/test.md'
    """
    abs_path = os.path.abspath(path)

    # Extract path starting from TEST_DOCS_DIR
    if TEST_DOCS_DIR in abs_path:
        file_path = abs_path[abs_path.rfind(TEST_DOCS_DIR):]
    else:
        # Fallback: use basename
        logger.warning(
            f"TEST_DOCS_DIR '{TEST_DOCS_DIR}' not found in path '{abs_path}', "
            "using basename"
        )
        file_path = os.path.basename(abs_path)

    # FIX: Actually assign the result of replace!
    file_path = file_path.replace('\\', '/')

    return f"{REPO_BASE_URL}/blob/{REPO_BRANCH}/{file_path}"


def path_to_folder(prefix: str, path: str) -> str:
    """
    Convert file path to Zephyr Scale folder path.

    Args:
        prefix: Team prefix
        path: File path

    Returns:
        Folder path for Zephyr Scale

    Example:
        >>> path_to_folder('VIS', '/project/test_plans/api/auth.md')
        '/VIS/api'
    """
    abs_path = os.path.abspath(path)
    folder = os.path.dirname(abs_path)

    # Extract folder relative to TEST_DOCS_DIR
    if TEST_DOCS_DIR in folder:
        folder = folder[folder.rfind(TEST_DOCS_DIR) + len(TEST_DOCS_DIR):]
    else:
        folder = ''

    folder = folder.replace('\\', '/')
    folder = folder.replace('.md', '')

    # Clean up folder path
    if folder and not folder.startswith('/'):
        folder = '/' + folder

    return f"/{prefix}{folder}" if folder else f"/{prefix}"


def get_tests(path: str, check_function) -> List[Any]:
    """
    Walk through directories and extract tests from markdown files.

    Args:
        path: File or directory path
        check_function: Function to process extracted tests

    Returns:
        List of processed tests
    """
    tests = []

    def _check(file_path: str) -> List:
        # Skip template files
        if file_path.endswith("tsxx-testsuite-brief-name.md"):
            return []

        logger.debug(f"Processing file: {file_path}")
        tests_from_md = md.parse_file_for_tests(file_path)
        return check_function(tests_from_md)

    if os.path.isfile(path):
        tests = _check(path)
    else:
        for root, dirs, files in os.walk(path):
            dirs.sort()
            for filename in sorted(files):
                if filename.endswith(".md"):
                    file_path = os.path.join(root, filename)
                    tests += _check(file_path)

    return tests


def create_tests(
    j: jira.Jira,
    tests_not_found: List,
    migration_mapping: Optional[Dict] = None
) -> None:
    """
    Interactively create missing test cases in Zephyr Scale.

    Args:
        j: Jira client instance
        tests_not_found: List of test cases to create
        migration_mapping: Optional mapping for migration (preserves ownership, status)
    """
    print(f'\n{len(tests_not_found)} test(s) not found. Should these be created?')
    answer = input("Enter 'Yes' to proceed: ")

    if answer.lower() != "yes":
        print("Skipping test creation.")
        return

    created_count = 0
    skipped_count = 0
    failed_count = 0

    for test in tests_not_found:
        print(f"\nCreating test case for: {test.title}")
        try:
            folder = path_to_folder(j.team, test.path)
            base_name = os.path.splitext(os.path.basename(test.path))[0]
            if base_name:
                folder = f"{folder}/{base_name}"
            url = path_to_url(test.path)
            description = f'<a href="{url}">{url}</a>'
            versions = ', '.join(sorted(test.versions)
                                 ) if test.versions else ''

            # if not versions:
            #     logger.warning(f"Skipping test {test.title} - no versions specified")
            #     skipped_count += 1
            #     continue

            # Get test category and type from summary
            test_category, test_type, test_component = \
                test_categories.summary_to_test_category(test.title)

            print(f"Derived category: {test_category}, type: {
                  test_type}, component: {test_component} for test {test.title}")

            # Validate that derived fields are not empty
            if not test_category or not test_type or not test_component:
                logger.warning(
                    f"Skipping test {
                        test.title} - unable to derive category/type/component from title")
                skipped_count += 1
                continue

            # Handle migration if mapping provided
            if migration_mapping:
                test_id = test.title.split(':', 1)[0]

                if test_id not in migration_mapping:
                    logger.info(
                        f"Skipping test case {test_id} (not in migration list)")
                    skipped_count += 1
                    continue

                j.add_test_case(
                    test.title,
                    folder,
                    description,
                    versions,
                    requirements=test.rtm,
                    priority=test.priority or 'P3',
                    owner=migration_mapping[test_id]['assignee'],
                    automated=migration_mapping[test_id]['automated'],
                    status=migration_mapping[test_id]['status'],
                )
            else:
                j.add_test_case(
                    test.title,
                    folder,
                    description,
                    versions,
                    requirements=test.rtm,
                    priority=test.priority or 'P3',
                    automated=test.automated if test.automated is not None else False,
                )

            created_count += 1

        except Exception as e:
            logger.error(f"Failed to create test {test.title}: {e}")
            failed_count += 1

    print(f"\n✅ Created: {created_count}")
    if skipped_count:
        print(f"⊘ Skipped: {skipped_count}")
    if failed_count:
        print(f"❌ Failed: {failed_count}")


def handle_potential_matches(
    j: jira.Jira,
    tests_with_matches: List[Tuple],
    auto_update: bool = False
) -> Tuple[int, int, int]:
    """
    Handle tests with potential matches interactively.

    Args:
        j: Jira client instance
        tests_with_matches: List of (test_md, matches) tuples
        auto_update: If True, auto-update high confidence matches

    Returns:
        Tuple of (updated_count, created_count, skipped_count)
    """
    updated_count = 0
    created_count = 0
    skipped_count = 0

    for test_md, matches in tests_with_matches:
        # Auto-update if confidence is very high and auto_update enabled
        if auto_update and matches[0][1] >= AUTO_UPDATE_THRESHOLD:
            jira_test = matches[0][0]
            logger.info(
                f"Auto-updating {jira_test['key']} (confidence: {matches[0][1]:.0%})")

            try:
                update_data = {
                    'name': test_md.title,
                    # CRITICAL: Preserve Team field
                    'customFields': {'Team': j.team}
                }
                j.update_test_case(jira_test['key'], update_data)
                print(
                    f"  ✅ Auto-updated {jira_test['key']} → {test_md.title.split(':', 1)[0]}")
                updated_count += 1
            except Exception as e:
                logger.error(f"Failed to update {jira_test['key']}: {e}")
                skipped_count += 1
            continue

        # Interactive mode
        print(f"\n{'=' * 80}")
        print(f"Markdown test: {test_md.title}")
        print(f"File: {test_md.path}")
        print(f"\nPotential matches in Jira:")

        for i, (jira_test, confidence, reason,
                match_type) in enumerate(matches, start=1):
            print(
                f"\n  {i}. {
                    jira_test['name']} ({
                    jira_test.get(
                        'key',
                        'N/A')})")
            print(f"     Confidence: {confidence:.0%} - {reason}")

        print(f"\nOptions:")
        print(f"  1-{len(matches)}: Update this Jira test to match markdown")
        print(f"  new: Create new test (ignore potential matches)")
        print(f"  skip: Skip this test for now")

        answer = input(f"\nYour choice: ").strip().lower()

        if answer == "skip":
            print("  Skipped")
            skipped_count += 1
            continue

        if answer == "new":
            print("  Creating new test...")
            try:
                folder = path_to_folder(j.team, test_md.path)
                base_name = os.path.splitext(os.path.basename(test_md.path))[0]
                if base_name:
                    folder = f"{folder}/{base_name}"
                url = path_to_url(test_md.path)
                description = f'<a href="{url}">{url}</a>'
                versions = ', '.join(
                    sorted(test_md.versions)) if test_md.versions else ''

                j.add_test_case(
                    test_md.title,
                    folder,
                    description,
                    versions,
                    requirements=test_md.rtm,
                    priority=test_md.priority or 'P3',
                    automated=test_md.automated if test_md.automated is not None else False,
                )
                print(f"  ✅ Created new test")
                created_count += 1
            except Exception as e:
                logger.error(f"Failed to create test: {e}")
                skipped_count += 1
            continue

        # Try to parse as number
        try:
            choice = int(answer)
            if 1 <= choice <= len(matches):
                jira_test = matches[choice - 1][0]

                # Info to delete test case from the markdown before updating
                # {jira_test['key']
                print(
                    f"\n⚠️  WARNING: Test case '{
                        jira_test['key']}' exists in Zephyr.")
                print(
                    f"You must DELETE this test from the markdown file BEFORE updating:")
                print(f"  File: {test_md.path}")
                print(f"  Test: {test_md.title}")
                print(
                    f"\nThis prevents: {
                        jira_test['name']} - from remaining in markdown.")

                confirm = input(
                    "\nHave you deleted the test from markdown? (yes/no): ").strip().lower()
                if confirm != "yes":
                    print(
                        "  Skipped. Please delete the test from markdown and try again.")
                    skipped_count += 1
                    continue

                print(f"  Updating {jira_test['key']} to match markdown...")

                try:
                    update_data = {
                        'name': test_md.title,
                        # CRITICAL: Preserve Team field
                        'customFields': {'Team': j.team}
                    }
                    j.update_test_case(jira_test['key'], update_data)
                    print(f"  ✅ Updated {jira_test['key']}")
                    updated_count += 1
                except Exception as e:
                    logger.error(f"Failed to update {jira_test['key']}: {e}")
                    skipped_count += 1
            else:
                print("  Invalid choice. Skipped.")
                skipped_count += 1
        except ValueError:
            print("  Invalid input. Skipped.")
            skipped_count += 1

    return updated_count, created_count, skipped_count


def check_zephyr_exists(
        path: str,
        jira_token: str,
        create: bool = False) -> bool:
    """
    Check if test cases exist in Zephyr Scale with smart matching.

    Uses multi-level matching strategy:
    1. Exact title match (100% confidence)
    2. Same file path (100% confidence)
    3. ID change only (90% confidence)
    4. Fuzzy summary match (60-80% confidence)

    Args:
        path: Path to markdown files
        jira_token: JIRA API token
        create: Whether to create missing tests

    Returns:
        True if tests were not found or have potential matches, False if all exact matches
    """
    j = jira.Jira(jira_token)

    migration_mapping = None  # Can be loaded from pickle if needed

    logger.info("Fetching existing tests from Zephyr Scale...")
    tests_from_jira = j.get_all_tests(fields="name,key,objective")
    logger.info(f"Found {len(tests_from_jira)} existing tests")

    # Build lookup by exact title for fast exact matches
    tests_by_title = {t['name']: t for t in tests_from_jira}

    def _check(tests_from_md: List) -> Tuple[List, List, List]:
        """
        Returns:
            (tests_found, tests_not_found, tests_with_matches)
        """
        tests_found = []
        tests_not_found = []
        tests_with_potential_matches = []

        for test in tests_from_md:
            test_id = test.title.split(':', 1)[0]

            # Quick exact match check
            if test.title in tests_by_title:
                print(f'✅ Zephyr found for: {test_id} ({test.path})')
                tests_found.append(test)
                continue

            # Smart matching for non-exact matches
            matches = find_test_matches(test, tests_from_jira)

            # if matches and matches[0][1] == 1.0 and matches[0][3] == 'file_path':
            #     # Found via file path (100% confidence)
            #     print(f'✅ Zephyr found for: {test_id} (via file path match) ({test.path})')
            #     tests_found.append(test)
            if matches and matches[0][1] >= 0.6:
                # Potential matches found (60%+ confidence)
                print(f'⚠️  Potential match(es) for: {test_id} ({test.path})')
                # Filter to top matches based on confidence
                if matches[0][1] >= 0.9:
                    # High confidence - show only top match
                    top_matches = matches[:1]
                else:
                    top_matches = matches[:min(3, len(matches))]  # Show top 3
                tests_with_potential_matches.append((test, top_matches))
            else:
                # No matches found
                print(f'❌ No Zephyr found for: {test_id} ({test.path})')
                tests_not_found.append(test)

        return tests_found, tests_not_found, tests_with_potential_matches

    # Process all markdown files
    all_results = []

    if os.path.isfile(path):
        tests_from_md = md.parse_file_for_tests(path)
        all_results.append(_check(tests_from_md))
    else:
        for root, dirs, files in os.walk(path):
            dirs.sort()
            for filename in sorted(files):
                if filename.endswith(".md") and not filename.endswith(
                        "tsxx-testsuite-brief-name.md"):
                    file_path = os.path.join(root, filename)
                    logger.debug(f"Processing file: {file_path}")
                    tests_from_md = md.parse_file_for_tests(file_path)
                    all_results.append(_check(tests_from_md))

    # Combine results
    tests_found = []
    tests_not_found = []
    tests_with_matches = []

    for found, not_found, with_matches in all_results:
        tests_found.extend(found)
        tests_not_found.extend(not_found)
        tests_with_matches.extend(with_matches)

    # Handle tests with potential matches
    if tests_with_matches:
        print(f"\n{'=' * 80}")
        print(f"⚠️  {len(tests_with_matches)} test(s) with potential matches")
        print(f"{'=' * 80}")

        updated, created, skipped = handle_potential_matches(
            j, tests_with_matches, auto_update=False)

        print(f"\n📊 Potential Matches Summary:")
        if updated:
            print(f"  ✅ Updated: {updated}")
        if created:
            print(f"  ✅ Created: {created}")
        if skipped:
            print(f"  ⊘ Skipped: {skipped}")

    # Handle tests not found
    if create and tests_not_found:
        create_tests(j, tests_not_found, migration_mapping)

    return len(tests_not_found) != 0 or len(tests_with_matches) != 0


def deprecate_tests(j: jira.Jira,
                    tests: List[Dict],
                    auto: bool = False) -> Tuple[int,
                                                 int]:
    """
    Mark tests as deprecated in Jira.

    Args:
        j: Jira client instance
        tests: List of test dictionaries to deprecate
        auto: If True, don't ask for confirmation

    Returns:
        Tuple of (success_count, failed_count)
    """
    if not auto and tests:
        print(f"\nThis will mark {len(tests)} test(s) as Deprecated:")
        for test in tests:
            print(f"  - {test['name']} ({test['key']})")
        confirm = input(f"\nProceed? (yes/no): ")
        if confirm.lower() != "yes":
            print("Cancelled")
            return 0, 0

    # deprecated_folder = "/Deprecated Tests"

    success_count = 0
    failed_count = 0

    for test in tests:
        try:
            update_data = {
                'status': 'Deprecated',
                # 'folder': deprecated_folder,
                'customFields': {
                    'Team': j.team  # CRITICAL: Preserve Team field
                }
            }

            # Add 'Orphaned' label
            current_labels = test.get('labels', [])
            if 'Orphaned' not in current_labels:
                current_labels.append('Orphaned')
                update_data['labels'] = current_labels

            j.update_test_case(test['key'], update_data)

            print(
                f"  ✅ Deprecated {
                    test['key']} → {
                    test['name'].split(
                        ':',
                        1)[0]}")
            success_count += 1

        except Exception as e:
            logger.error(f"Failed to deprecate {test['key']}: {e}")
            print(f"  ❌ Failed to deprecate {test['key']}: {e}")
            failed_count += 1

    return success_count, failed_count


def handle_orphaned_tests_interactive(
        j: jira.Jira,
        orphaned: List[Dict]) -> None:
    """
    Interactively handle orphaned tests.

    Args:
        j: Jira client instance
        orphaned: List of orphaned test dictionaries
    """
    print("\nOptions:")
    print(f"  1-{len(orphaned)}: Mark this test as deprecated")
    print(f"  all: Mark all as deprecated")
    print(f"  skip: Skip this batch")
    print(f"  exit: Exit without changes")

    while True:
        answer = input("\nYour choice: ").strip().lower()

        if answer == "exit":
            print("Exited without changes")
            return

        if answer == "skip":
            print("Skipped all orphaned tests")
            return

        if answer == "all":
            print(f"\nDeprecating all {len(orphaned)} tests...")
            success, failed = deprecate_tests(j, orphaned, auto=False)
            print(f"\n📊 Summary:")
            print(f"  ✅ Deprecated: {success}")
            if failed:
                print(f"  ❌ Failed: {failed}")
            return

        # Try to parse as number
        try:
            choice = int(answer)
            if 1 <= choice <= len(orphaned):
                test = orphaned[choice - 1]
                print(f"\nDeprecating {test['key']}...")
                success, failed = deprecate_tests(j, [test], auto=False)
                if success:
                    print("✅ Done")
                    # Remove from list
                    orphaned.pop(choice - 1)
                    if not orphaned:
                        print("\nAll orphaned tests processed!")
                        return
                    # Show remaining
                    print(f"\n{len(orphaned)} orphaned test(s) remaining")
            else:
                print("Invalid choice")
        except ValueError:
            print("Invalid input")


def detect_orphaned_tests(
    path: str,
    jira_token: str,
    report_only: bool = False,
    auto_deprecate: bool = False
) -> bool:
    """
    Detect tests that exist in Jira but not in markdown.

    Tests are considered orphaned if:
    - They exist in Jira (in the scanned folder scope)
    - Their ID doesn't exist in any markdown file
    - They don't match any markdown test via smart matching (90%+ confidence)
    - They're not already marked as Deprecated

    Args:
        path: Path to markdown files
        jira_token: JIRA API token
        report_only: Only report, don't make changes
        auto_deprecate: Automatically deprecate without asking

    Returns:
        True if orphaned tests were found, False otherwise
    """
    j = jira.Jira(jira_token)

    logger.info("Parsing markdown files...")
    tests_from_md = []

    if os.path.isfile(path):
        tests_from_md = md.parse_file_for_tests(path)
    else:
        for root, dirs, files in os.walk(path):
            dirs.sort()
            for filename in sorted(files):
                if filename.endswith(".md") and not filename.endswith(
                        "tsxx-testsuite-brief-name.md"):
                    file_path = os.path.join(root, filename)
                    logger.debug(f"Parsing: {file_path}")
                    tests_from_md.extend(md.parse_file_for_tests(file_path))

    logger.info(f"Found {len(tests_from_md)} tests in markdown")

    # Determine folder scope for fetching Jira tests efficiently
    # folder_scope = None
    folder_scope = "SceneScape"
    if os.path.isdir(path):
        # Convert directory path to Jira folder
        # e.g., test_plans/api → /Vis/api
        abs_path = os.path.abspath(path)

        # Extract folder relative to TEST_DOCS_DIR
        if TEST_DOCS_DIR in abs_path:
            rel_folder = abs_path[abs_path.rfind(
                TEST_DOCS_DIR) + len(TEST_DOCS_DIR):]
        else:
            rel_folder = ''

        rel_folder = rel_folder.replace('\\', '/').lstrip('/')

        # if rel_folder:
        #     folder_scope = f"/{j.team}/{rel_folder}"
        # else:
        #     folder_scope = f"/{j.team}"

    # Fetch tests from Jira - use folder-scoped query for efficiency
    if folder_scope:
        logger.info(f"Fetching tests in folder scope: {folder_scope}")
        tests_from_jira = j.get_tests_in_folder(
            folder_scope, fields="name,key,status,folder,updatedOn,labels")
    else:
        logger.info("Fetching all tests from Jira...")
        tests_from_jira = j.get_all_tests(
            fields="name,key,status,folder,updatedOn,labels")

    logger.info(f"Found {len(tests_from_jira)} tests in Jira (folder-scoped)")

    # Build set of markdown test IDs
    md_test_ids = {
        test.title.split(
            ':',
            1)[0] for test in tests_from_md if ':' in test.title}

    # Find orphaned tests
    orphaned = []
    already_deprecated = 0

    for jira_test in tests_from_jira:
        # Skip if already deprecated
        if jira_test.get('status') == 'Deprecated':
            already_deprecated += 1
            continue

        jira_title = jira_test.get('name', '')
        if ':' not in jira_title:
            continue

        jira_id = jira_title.split(':', 1)[0]

        # Check if ID exists in markdown
        if jira_id in md_test_ids:
            continue

        # Check if smart match exists (high confidence)
        # Create a mock test object for matching
        class JiraTestWrapper:
            def __init__(self, title):
                self.title = title
                self.path = ''

        jira_wrapper = JiraTestWrapper(jira_title)
        matches = find_test_matches(jira_wrapper, tests_from_jira)

        # If high confidence match exists, not orphaned (probably renamed)
        if matches and matches[0][1] >= 0.9:
            # Check if the matched test exists in markdown
            matched_jira_id = matches[0][0]['name'].split(':', 1)[0]
            if matched_jira_id in md_test_ids:
                continue  # Not orphaned - it's a rename that's handled by smart matching

        # This test is orphaned
        orphaned.append(jira_test)

    # Report findings
    print(f"\n{'=' * 80}")
    if not orphaned:
        print("✅ No orphaned tests found!")
        print(f"   Jira: {len(tests_from_jira)} tests")
        print(f"   Markdown: {len(tests_from_md)} tests")
        if already_deprecated:
            print(f"   Already deprecated: {already_deprecated} tests")
        print(f"{'=' * 80}\n")
        return False

    print(f"⚠️  Found {len(orphaned)} orphaned test(s)")
    print(f"   (Tests in Jira but not in markdown)")
    print(f"{'=' * 80}\n")

    # Show details
    for i, test in enumerate(orphaned, start=1):
        print(f"{i}. {test['name']} ({test['key']})")
        print(f"   Last modified: {test.get('updatedOn', 'Unknown')}")
        print(f"   Status: {test.get('status', 'Unknown')}")
        print(f"   Folder: {test.get('folder', 'Unknown')}")
        print()

    if report_only:
        print("=" * 80)
        print("No changes made (--report-only mode)")
        print("\nTo deprecate these tests, run:")
        print(
            f"  python check_zephyr_exists.py --jira-token $TOKEN --detect-orphaned --auto-deprecate {path}")
        return True

    # Handle deprecation
    if auto_deprecate:
        print("Auto-deprecating all orphaned tests...\n")
        success, failed = deprecate_tests(j, orphaned, auto=True)
        print(f"\n📊 Summary:")
        print(f"  ✅ Deprecated: {success}")
        if failed:
            print(f"  ❌ Failed: {failed}")
    else:
        # Interactive mode
        handle_orphaned_tests_interactive(j, orphaned)

    return True


def update_zephyr_fields(
    path: str,
    jira_token: str,
    update: bool,
    automation: Optional[bool] = None,
    affected_versions: Optional[List[str]] = None
) -> None:
    """
    Validate and optionally update test case fields in Zephyr Scale.

    Args:
        path: Path to markdown files
        jira_token: JIRA API token
        update: Whether to actually update fields
        automation: Whether to set automation flag (None = don't change)
        affected_versions: Override affected versions (None = use markdown)
    """
    j = jira.Jira(jira_token)

    check_verbose = False  # Set to True for detailed output

    logger.info("Fetching existing tests from Zephyr Scale...")
    test_from_jira = j.get_all_tests_as_lut()
    logger.info(f"Found {len(test_from_jira)} existing tests")

    # Get list of defects to exclude from RTM
    logger.info("Fetching defects list...")
    defects_list = j.get_all_defects_as_lut().keys()
    logger.info(f"Found {len(defects_list)} defects")

    def _check(tests_from_md: List) -> List[Tuple]:
        tests = []

        for test in tests_from_md:
            test_id = test.title.split(':', 1)[0]
            if test_id in test_from_jira:
                if check_verbose:
                    print(f'✅ Zephyr found for: {test_id}')
                tests.append((test_from_jira[test_id], test))
            else:
                print(f'❌ No Zephyr found for: {test_id} ({test.path})')

        return tests

    update_count = 0
    issues_count = 0

    for test_jira, test_md in get_tests(path, _check):
        report, update_data = check_zephyr_fields(
            j, defects_list, test_jira, test_md, check_verbose, automation, affected_versions)

        if report:
            issues_count += 1
            print("")
            print(f"Test case: {report['key']} {report['summary']}")
            print(f"File: {report['file']}")
            print(f"Owner: {report['owner']}")
            for line in report['report']:
                print(line)

        # Update if requested and there are changes
        if update:
            has_changes = (
                len(update_data) > 1 or (
                    update_data.get('customFields') and len(
                        update_data['customFields']) > 0))
            if has_changes:
                try:
                    # Ensure Team custom field is always included
                    if 'customFields' not in update_data:
                        update_data['customFields'] = {}
                    update_data['customFields']['Team'] = j.team
                    j.update_test_case(test_jira['key'], update_data)
                    update_count += 1
                except Exception as e:
                    logger.error(f"Failed to update {test_jira['key']}: {e}")

    print(f"\n📊 Summary:")
    print(f"  Test cases with issues: {issues_count}")
    if update:
        print(f"  Test cases updated: {update_count}")


def check_zephyr_fields(
    j: jira.Jira,
    defects_list: List[str],
    test_jira: Dict,
    test_md: Any,
    check_verbose: bool = False,
    automation: Optional[bool] = None,
    affected_versions: Optional[List[str]] = None
) -> Tuple[Dict, Dict]:
    """
    Validate test case fields against markdown source.

    Args:
        j: Jira client instance
        defects_list: List of defect keys to exclude from RTM
        test_jira: Test data from Zephyr Scale
        test_md: Test data from markdown
        check_verbose: Whether to report successes
        automation: Whether to check/set automation flag (None = don't change)
        affected_versions: Override affected versions (None = use markdown)

    Returns:
        Tuple of (report_dict, update_data)
    """
    report = []

    issue_key = test_jira['key']
    summary = test_jira['name']
    sscape_key, sscape_title = summary.split(':', 1)

    update_data: Dict[str, Any] = {'customFields': {}}

    # CRITICAL: Always include Team field to prevent it from being cleared
    # Jira may clear custom fields that are not included in the update request
    # update_data['customFields']['Team'] = j.team

    # Validate title
    test_title_jira = summary
    test_title_target = test_md.title

    if test_title_jira == test_title_target:
        if check_verbose:
            report.append(f'✅ Title: {test_title_target}')
    else:
        report.append(f'❌ Title: expected: {
                      test_title_target} / found: {test_title_jira}')
        update_data['name'] = test_title_target

    # Validate description
    test_description_jira = test_jira['objective']
    url = path_to_url(test_md.path)
    test_description_target = f'<a href="{url}">{url}</a>'

    if test_description_jira == test_description_target:
        if check_verbose:
            report.append(f'✅ Description: {test_description_target}')
    else:
        report.append(f'❌ Description: expected: {
                      test_description_target} / found: {test_description_jira}')
        update_data['objective'] = test_description_target

    # Validate folder
    test_folder_jira = test_jira.get('folder', '')
    test_folder_target = path_to_folder(jira.Jira.team, test_md.path)
    base_name = os.path.splitext(os.path.basename(test_md.path))[0]
    if base_name:
        test_folder_target = f"{test_folder_target}/{base_name}"

    if test_folder_jira == test_folder_target:
        if check_verbose:
            report.append(f'✅ Folder: {test_folder_target}')
    else:
        report.append(f'❌ Folder: expected: {
                      test_folder_target} / found: {test_folder_jira}')
        update_data['folder'] = test_folder_target

    # Validate category, type, component
    test_category_jira = test_jira['customFields'].get('Test Category', '')
    test_type_jira = test_jira['customFields'].get('Test Type', '')
    test_components_jira = test_jira.get('component', '')

    test_category_target, test_type_target, test_component_target = \
        test_categories.summary_to_test_category(summary)

    if test_category_jira == test_category_target:
        if check_verbose:
            report.append(f'✅ Test Category: {test_category_target}')
    else:
        report.append(f'❌ Test Category: expected: {
                      test_category_target} / found: {test_category_jira}')
        update_data['customFields']['Test Category'] = test_category_target

    if test_type_jira == test_type_target:
        if check_verbose:
            report.append(f'✅ Test Type: {test_type_target}')
    else:
        report.append(f'❌ Test Type: expected: {
                      test_type_target} / found: {test_type_jira}')
        # FIX: This was assigning test_category_target instead of
        # test_type_target!
        update_data['customFields']['Test Type'] = test_type_target  # FIXED

    if test_component_target in test_components_jira:
        if check_verbose:
            report.append(f'✅ Test Component: {test_component_target}')
    else:
        report.append(f'❌ Test Component: expected: {
                      test_component_target} / found: {test_components_jira}')
        update_data['component'] = test_component_target

    # Validate ID custom field
    id_jira = test_jira['customFields'].get('ID', '')
    # Extract ID from markdown title (e.g., "Vis/API/001")
    id_target = test_md.title.split(':', 1)[0]

    if id_jira == id_target:
        if check_verbose:
            report.append(f'✅ ID: {id_target}')
    else:
        report.append(f'❌ ID: expected: {id_target} / found: {id_jira}')
        update_data['customFields']['ID'] = id_target

    # Validate priority
    if test_md.priority:
        priority_jira = test_jira.get('priority', '')
        priority_target = test_md.priority

        if priority_jira == priority_target:
            if check_verbose:
                report.append(f'✅ Priority: {priority_target}')
        else:
            report.append(f'❌ Priority: expected: {
                          priority_target} / found: {priority_jira}')
            update_data['priority'] = priority_target

    # Validate RTM (requirements)
    test_rtm_jira = sorted(test_jira.get('issueLinks', []))
    test_rtm_target = sorted(test_md.rtm)

    # Exclude defects from RTM comparison
    test_rtm_jira = [
        issue for issue in test_rtm_jira if issue not in defects_list]

    if test_rtm_jira == test_rtm_target:
        if check_verbose:
            report.append(f'✅ Requirements: {test_rtm_target}')
    else:
        report.append(f'❌ Requirements: expected: {
                      test_rtm_target} / found: {test_rtm_jira}')
        update_data['issueLinks'] = test_rtm_target

    # Validate automation
    # Priority order:
    # 1. Command line flag (--automation true/false) - overrides everything
    # 2. Markdown field (Automated: yes/no) - sets the expected value
    # 3. Current Jira value - only checked if neither 1 nor 2 are set

    test_automation_jira = test_jira['customFields'].get('Automated', False)

    # Determine target value
    if automation is not None:
        # Command line override
        test_automation_target = automation
    elif test_md.automated is not None:
        # Use markdown value
        test_automation_target = test_md.automated
    else:
        # No target specified, skip validation
        test_automation_target = None

    # Only validate if we have a target value
    if test_automation_target is not None:
        if test_automation_jira != test_automation_target:
            report.append(f'❌ Automated: expected: {
                          test_automation_target} / found: {test_automation_jira}')
            update_data['customFields']['Automated'] = test_automation_target
        elif check_verbose:
            report.append(f'✅ Automated: {test_automation_target}')

    # Validate labels
    labels_jira = sorted(test_jira.get('labels', []))
    labels_target = jira.Jira.summary_to_test_case_labels(
        sscape_key) + [test_category_target, test_type_target]

    # Add 'Automated' label if test should be automated
    # Use target value if available, otherwise use current Jira value
    if test_automation_target is not None:
        if test_automation_target:
            labels_target.append('Automated')
    elif test_automation_jira:
        labels_target.append('Automated')

    # Replace spaces with underscores (Zephyr Scale requirement)
    labels_target = [label.replace(' ', '_') for label in labels_target]
    labels_target = sorted(labels_target)

    if labels_jira == labels_target:
        if check_verbose:
            report.append(f'✅ Labels: {labels_target}')
    else:
        report.append(f'❌ Labels: expected: {
                      labels_target} / found: {labels_jira}')
        update_data['labels'] = labels_target

    # Validate status
    status_jira = test_jira['status']
    status_target_versions = test_md.versions

    if 'SP-CLOSED' in status_target_versions:
        status_target = 'Deprecated'
    else:
        status_target = 'Approved'

    if status_jira == status_target:
        if check_verbose:
            report.append(f'✅ Status: {status_target}')
    else:
        report.append(f'❌ Status: expected: {
                      status_target} / found: {status_jira}')
        update_data['status'] = status_target

    # Validate versions (skip for deprecated tests)
    if 'SP-CLOSED' not in status_target_versions:
        versions_jira = test_jira['customFields'].get('Affected Versions', '')
        versions_jira = ', '.join(sorted(v.strip()
                                  for v in versions_jira.split(', ') if v.strip()))

        # Use command line override if provided, otherwise use markdown
        # versions
        if affected_versions is not None:
            versions_target = ', '.join(sorted(affected_versions))
        else:
            versions_target = ', '.join(sorted(test_md.versions))

        if versions_jira == versions_target:
            if check_verbose:
                report.append(f'✅ Versions: {versions_target}')
        else:
            report.append(f'❌ Versions: expected: {
                          versions_target} / found: {versions_jira}')
            update_data['customFields']['Affected Versions'] = versions_target

    # Build report dictionary
    report_dict = {}
    if report:
        report_dict['key'] = issue_key
        report_dict['summary'] = summary
        report_dict['file'] = os.path.relpath(
            test_md.path,
            os.path.join(os.path.dirname(__file__), '..')
        )
        report_dict['owner'] = j.get_user_displayname_from_userkey(
            test_jira['owner'])
        report_dict['report'] = report

    return report_dict, update_data


def detect_renumber(path: str, jira_token: str) -> None:
    """
    Detect and handle test case renumbering.

    Args:
        path: Path to markdown files
        jira_token: JIRA API token
    """
    j = jira.Jira(jira_token)

    logger.info("Fetching existing tests from Zephyr Scale...")
    tests_from_jira = j.get_all_tests(fields="name,key")
    logger.info(f"Found {len(tests_from_jira)} existing tests")

    tests_from_jira_by_title = {t['name']: t for t in tests_from_jira}

    # Build lookup by summary (handle collisions)
    tests_from_jira_by_summary = defaultdict(list)
    for t in tests_from_jira:
        try:
            summary = t['name'].split(':', 1)[1]
            tests_from_jira_by_summary[summary].append(t)
        except IndexError:
            logger.warning(
                f"Test {
                    t.get(
                        'key',
                        'unknown')} has invalid name format")

    def _check(tests_from_md: List) -> List:
        tests = []

        for test in tests_from_md:
            if test.title in tests_from_jira_by_title:
                print(f'✅ Zephyr found for: {test.title.split(":", 1)[0]}')
            else:
                print(f'❌ No Zephyr found for: {test.title.split(":", 1)[0]}')
                tests.append(test)

        return tests

    tests_not_found = get_tests(path, _check)

    rename_count = 0
    skip_count = 0

    for test in tests_not_found:
        test_id, test_summary = test.title.split(':', 1)
        print("\nCan't find test case:")
        print(f'   {test.title}')

        if test_summary in tests_from_jira_by_summary:
            jira_tests = tests_from_jira_by_summary[test_summary]

            print("\n  Tests found with the same summary:")
            for i, jira_test in enumerate(jira_tests, start=1):
                jira_key = jira_test['key']
                jira_summary = jira_test['name']
                print(f"  {i}. {jira_summary} ({jira_key})")

            answer = input(
                "\n  Enter the number of the test to rename, or 'No' to skip: ")

            if answer.lower() == "no":
                print("  Skipping rename.")
                skip_count += 1
                continue

            # Handle simple "yes" for single match
            if len(jira_tests) == 1 and answer.lower() == "yes":
                index = 0
            else:
                try:
                    index = int(answer) - 1
                except ValueError:
                    print("  Invalid input. Skipping rename.")
                    skip_count += 1
                    continue

            if 0 <= index < len(jira_tests):
                jira_test = jira_tests[index]
                jira_key = jira_test['key']

                try:
                    update_data = {
                        'name': test.title,
                        # CRITICAL: Preserve Team field
                        'customFields': {'Team': j.team}
                    }
                    j.update_test_case(jira_key, update_data)
                    print(f"  ✅ Renamed {jira_key} to {test.title}")
                    rename_count += 1
                except Exception as e:
                    logger.error(f"  Failed to rename {jira_key}: {e}")
            else:
                print("  Invalid input. Skipping rename.")
                skip_count += 1
        else:
            skip_count += 1

    print(f"\n📊 Summary:")
    print(f"  Renamed: {rename_count}")
    print(f"  Skipped: {skip_count}")


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Synchronize markdown test documentation with Zephyr Scale",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check if tests exist
  %(prog)s --jira-token TOKEN path/to/tests

  # Create missing tests
  %(prog)s --jira-token TOKEN --create path/to/tests

  # Validate and update fields
  %(prog)s --jira-token TOKEN --check-fields --update path/to/tests

  # Set automation flag
  %(prog)s --jira-token TOKEN --check-fields --update --automation true path/to/tests

  # Detect renumbering
  %(prog)s --jira-token TOKEN --detect-renumber path/to/tests
        """)

    parser.add_argument(
        '--debug',
        help="Enable debug logging",
        action='store_true'
    )

    parser.add_argument(
        '-a', '--jira-token',
        help="JIRA API personal access token (or set JIRA_TOKEN env var)",
        default=os.environ.get('JIRA_TOKEN') or None,
        required=not bool(os.environ.get('JIRA_TOKEN')),
        action='store'
    )

    parser.add_argument(
        "path",
        help="Path to markdown files to check",
        type=str,
        action="store"
    )

    exists_group = parser.add_argument_group('check exists')
    exists_group.add_argument(
        '--create',
        help="Create test cases that don't exist in Zephyr",
        action='store_true'
    )

    renumber = parser.add_argument_group('detect renumber')
    renumber.add_argument(
        '--detect-renumber',
        help="Attempt to detect renumbering of tests",
        action='store_true'
    )

    fields_group = parser.add_argument_group('check fields')
    fields_group.add_argument(
        '--check-fields',
        help="Check all fields for all tickets",
        action='store_true'
    )
    fields_group.add_argument(
        '--update',
        help="Update fields (requires --check-fields)",
        action='store_true'
    )
    fields_group.add_argument(
        '--automation',
        help="Set automation flag (true/false)",
        type=str,
        default=None,
        action="store"
    )
    fields_group.add_argument(
        '--affected-versions',
        help="Override affected versions (comma-separated, e.g., '2026.1,2026.2')",
        type=str,
        default=None,
        action="store")

    orphaned_group = parser.add_argument_group('detect orphaned tests')
    orphaned_group.add_argument(
        '--detect-orphaned',
        help="Detect tests that exist in Jira but not in markdown",
        action='store_true'
    )
    orphaned_group.add_argument(
        '--auto-deprecate',
        help="Automatically deprecate orphaned tests (use with --detect-orphaned)",
        action='store_true')
    orphaned_group.add_argument(
        '--report-only',
        help="Only report orphaned tests, do not make changes (use with --detect-orphaned)",
        action='store_true')

    args = parser.parse_args()

    # Parse automation flag: convert string to boolean or None
    if args.automation is not None:
        args.automation = args.automation.lower() == "true"

    # Parse affected versions: convert comma-separated string to list
    if args.affected_versions is not None:
        args.affected_versions = [v.strip()
                                  for v in args.affected_versions.split(',')]

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if not os.path.exists(args.path):
        print(f"❌ Path '{args.path}' not found")
        sys.exit(2)

    logger.info(f"Configuration:")
    logger.info(f"  REPO_BASE_URL: {REPO_BASE_URL}")
    logger.info(f"  TEST_DOCS_DIR: {TEST_DOCS_DIR}")
    logger.info(f"  REPO_BRANCH: {REPO_BRANCH}")

    try:
        if args.detect_orphaned:
            # Detect orphaned tests
            found = detect_orphaned_tests(
                args.path,
                args.jira_token,
                report_only=args.report_only,
                auto_deprecate=args.auto_deprecate
            )
            if found and not args.report_only:
                sys.exit(0)  # Found and handled
            elif found:
                sys.exit(1)  # Found but only reported
        elif args.detect_renumber:
            detect_renumber(args.path, args.jira_token)
        elif args.check_fields:
            update_zephyr_fields(
                args.path,
                args.jira_token,
                args.update,
                args.automation,
                args.affected_versions)
        else:
            error = check_zephyr_exists(
                args.path, args.jira_token, args.create)
            if not args.create and error:
                sys.exit(1)
    except md.MarkdownParseException as e:
        logger.error(f"Markdown parsing error: {e}")
        sys.exit(1)
    except jira.JiraException as e:
        logger.error(f"JIRA API error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
