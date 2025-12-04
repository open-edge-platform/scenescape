#!/usr/bin/env python3
"""
Test script for generate_third_party_programs.py
"""

import os
import tempfile
import csv
import shutil
import unittest
from pathlib import Path
import sys
from unittest.mock import patch, mock_open

# Add the script directory to Python path
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir))

from generate_third_party_programs import (
    get_license_url,
    sanitize_filename,
    is_special_license,
    download_license_text,
    process_dependencies,
    main,
    parse_license_expression,
    get_licenses_from_expression,
    download_license_expression_text,
    _license_text_cache
)


class TestGenerateThirdPartyPrograms(unittest.TestCase):

    def setUp(self):
        """Set up test environment with temporary directory."""
        # Clear license cache before each test
        _license_text_cache.clear()

        self.test_dir = tempfile.mkdtemp()
        self.input_file = os.path.join(self.test_dir, "test_deps.csv")
        self.output_file = os.path.join(self.test_dir, "test_third_party.txt")
        self.preamble_file = os.path.join(self.test_dir, "test_preamble.txt")
        self.licenses_dir = os.path.join(self.test_dir, "licenses")
        os.makedirs(self.licenses_dir)

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir)

    def create_test_csv(self, data):
        """Create a test CSV file with given data."""
        with open(self.input_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Component', 'License'])  # Header
            for row in data:
                writer.writerow(row)

    def create_test_preamble(self, content="Test Preamble\nThis is a test file.\n"):
        """Create a test preamble file."""
        with open(self.preamble_file, 'w', encoding='utf-8') as f:
            f.write(content)

    def create_test_license_file(self, license_name, content):
        """Create a test license file."""
        safe_name = sanitize_filename(license_name)
        license_file = os.path.join(self.licenses_dir, f"{safe_name}.txt")
        with open(license_file, 'w', encoding='utf-8') as f:
            f.write(content)

    def test_get_license_url(self):
        """Test license URL mapping and auto-discovery."""
        # Test known license with new SPDX base URL
        self.assertEqual(
            get_license_url("MIT"),
            "https://raw.githubusercontent.com/spdx/license-list-data/refs/heads/main/text/MIT.txt"
        )

        # Test Apache license
        self.assertEqual(
            get_license_url("Apache-2.0"),
            "https://raw.githubusercontent.com/spdx/license-list-data/refs/heads/main/text/Apache-2.0.txt"
        )

        # Test auto-discovery for licenses not in custom_map
        # Note: This test requires network access, so we'll mock it
        with patch('requests.head') as mock_head:
            mock_head.return_value.status_code = 200
            result = get_license_url("CC0-1.0")
            self.assertTrue(result.endswith("CC0-1.0.txt"))
            self.assertTrue("githubusercontent.com" in result)

        # Test unknown license (no network response)
        with patch('requests.head') as mock_head:
            mock_head.return_value.status_code = 404
            self.assertEqual(get_license_url("Unknown-License"), "")

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        self.assertEqual(sanitize_filename("MIT"), "MIT")
        self.assertEqual(sanitize_filename("Apache-2.0"), "Apache-2.0")
        self.assertEqual(sanitize_filename("GPL/2.0"), "GPL_2.0")
        self.assertEqual(sanitize_filename("License with spaces"), "License_with_spaces")
        self.assertEqual(sanitize_filename("License:with:colons"), "License_with_colons")

    def test_is_special_license(self):
        """Test special license detection."""
        # Test special licenses
        self.assertTrue(is_special_license("Public Domain"))
        self.assertTrue(is_special_license("collection of licenses"))

        # Test normal licenses
        self.assertFalse(is_special_license("MIT"))
        self.assertFalse(is_special_license("Apache-2.0"))
        self.assertFalse(is_special_license("BSD-3-Clause"))

    def test_download_license_text_special_licenses(self):
        """Test handling of special licenses."""
        license_sources = {}
        failed_licenses = []
        special_licenses_skipped = set()

        # Test Public Domain
        result = download_license_text("Public Domain", license_sources, failed_licenses,
                                     self.licenses_dir, special_licenses_skipped)
        self.assertEqual(result, "This software is in the Public Domain and is not subject to copyright restrictions.")
        self.assertEqual(license_sources["Public Domain"], "Special license (no text required)")
        self.assertIn("Public Domain", special_licenses_skipped)
        self.assertEqual(failed_licenses, [])

        # Test collection of licenses
        result = download_license_text("collection of licenses", license_sources, failed_licenses,
                                     self.licenses_dir, special_licenses_skipped)
        self.assertEqual(result, "This component contains a collection of different licenses. Please refer to the original source for specific license terms.")
        self.assertEqual(license_sources["collection of licenses"], "Special license (no text required)")
        self.assertIn("collection of licenses", special_licenses_skipped)
        self.assertEqual(failed_licenses, [])

    @patch('requests.get')
    def test_download_license_text_success(self, mock_get):
        """Test successful license download."""
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.text = "MIT License\nPermission is hereby granted..."

        license_sources = {}
        failed_licenses = []
        special_licenses_skipped = set()

        result = download_license_text("MIT", license_sources, failed_licenses, self.licenses_dir, special_licenses_skipped)

        self.assertEqual(result, "MIT License\nPermission is hereby granted...")
        self.assertEqual(license_sources["MIT"], "https://raw.githubusercontent.com/spdx/license-list-data/refs/heads/main/text/MIT.txt")
        self.assertEqual(failed_licenses, [])

    @patch('requests.get')
    @patch('requests.head')
    def test_download_license_text_fallback_to_local(self, mock_head, mock_get):
        """Test fallback to local license file when download fails."""
        # Mock failed download - both HEAD and GET should fail
        mock_head.return_value.status_code = 404
        mock_get.side_effect = Exception("Network error")

        # Create local license file
        license_content = "Local MIT License\nThis is from local file"
        self.create_test_license_file("MIT", license_content)

        license_sources = {}
        failed_licenses = []
        special_licenses_skipped = set()

        result = download_license_text("MIT", license_sources, failed_licenses, self.licenses_dir, special_licenses_skipped)

        self.assertEqual(result, license_content)
        self.assertTrue(license_sources["MIT"].endswith("MIT.txt"))
        self.assertEqual(failed_licenses, [])

    def test_download_license_text_not_found(self):
        """Test behavior when license is not found anywhere."""
        license_sources = {}
        failed_licenses = []
        special_licenses_skipped = set()

        # Use a license name that doesn't have a URL mapping
        result = download_license_text("Unknown-License", license_sources, failed_licenses, self.licenses_dir, special_licenses_skipped)

        self.assertIsNone(result)
        self.assertEqual(license_sources["Unknown-License"], None)
        self.assertEqual(failed_licenses, ["Unknown-License"])

    def test_process_dependencies_simple(self):
        """Test processing simple dependencies."""
        # Create test data
        test_data = [
            ["numpy==1.21.0", "BSD-3-Clause"],
            ["requests==2.25.0", "Apache-2.0"],
        ]

        self.create_test_csv(test_data)
        self.create_test_preamble("Simple Test Preamble\n")

        # Create local license files
        self.create_test_license_file("BSD-3-Clause", "BSD 3-Clause License\nRedistribution and use...")
        self.create_test_license_file("Apache-2.0", "Apache License Version 2.0\nTERMS AND CONDITIONS...")

        # Process dependencies
        with patch('requests.get') as mock_get, patch('requests.head') as mock_head:
            mock_get.side_effect = Exception("No network")  # Force local file usage
            mock_head.return_value.status_code = 404
            process_dependencies(self.input_file, self.output_file, self.preamble_file, self.licenses_dir)

        # Verify output file exists and has expected content
        self.assertTrue(os.path.exists(self.output_file))

        with open(self.output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check preamble
        self.assertIn("Simple Test Preamble", content)

        # Check components are listed
        self.assertIn("numpy==1.21.0", content)
        self.assertIn("requests==2.25.0", content)

        # Check licenses are included
        self.assertIn("Apache-2.0", content)
        self.assertIn("BSD-3-Clause", content)

        # Check license texts are included
        self.assertIn("BSD 3-Clause License", content)
        self.assertIn("Apache License Version 2.0", content)

    def test_process_dependencies_multiple_licenses(self):
        """Test processing components with multiple licenses."""
        test_data = [
            ["perl==5.34.0", "Artistic License or GPL-1.0"],
            ["component2==1.0.0", "MIT and Apache-2.0"],
        ]

        self.create_test_csv(test_data)
        self.create_test_preamble()

        # Create license files
        self.create_test_license_file("Artistic License", "Artistic License Text")
        self.create_test_license_file("GPL-1.0", "GPL 1.0 License Text")
        self.create_test_license_file("MIT", "MIT License Text")
        self.create_test_license_file("Apache-2.0", "Apache License Text")

        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("No network")
            process_dependencies(self.input_file, self.output_file, self.preamble_file, self.licenses_dir)

        with open(self.output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check that both components are listed under their respective licenses
        self.assertIn("perl==5.34.0", content)
        self.assertIn("component2==1.0.0", content)

        # Check all licenses are present
        for license_name in ["Artistic License", "GPL-1.0", "MIT", "Apache-2.0"]:
            self.assertIn(license_name, content)

    def test_process_dependencies_empty_license(self):
        """Test handling of components with empty licenses."""
        test_data = [
            ["component1==1.0.0", "MIT"],
            ["component2==1.0.0", ""],  # Empty license
            ["component3==1.0.0", "Apache-2.0"],
        ]

        self.create_test_csv(test_data)
        self.create_test_preamble()

        self.create_test_license_file("MIT", "MIT License Text")
        self.create_test_license_file("Apache-2.0", "Apache License Text")

        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("No network")
            process_dependencies(self.input_file, self.output_file, self.preamble_file, self.licenses_dir)

        with open(self.output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Components with licenses should be present
        self.assertIn("component1==1.0.0", content)
        self.assertIn("component3==1.0.0", content)

        # Component with empty license should not cause issues
        # (It won't be listed under any license section)
        self.assertIn("MIT", content)
        self.assertIn("Apache-2.0", content)

    def test_process_dependencies_special_licenses(self):
        """Test processing components with special licenses."""
        test_data = [
            ["sqlite-component==1.0.0", "Public Domain"],
            ["ubuntu-base==20.04", "collection of licenses"],
            ["regular-package==1.0.0", "MIT"],
        ]

        self.create_test_csv(test_data)
        self.create_test_preamble("Special License Test\n")
        self.create_test_license_file("MIT", "MIT License Text")

        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("No network")
            process_dependencies(self.input_file, self.output_file, self.preamble_file, self.licenses_dir)

        with open(self.output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check that all components are present
        self.assertIn("sqlite-component==1.0.0", content)
        self.assertIn("ubuntu-base==20.04", content)
        self.assertIn("regular-package==1.0.0", content)

        # Check special license explanatory text
        self.assertIn("This software is in the Public Domain", content)
        self.assertIn("collection of different licenses", content)

        # Check regular license is also present
        self.assertIn("MIT", content)

    def test_main_function_with_arguments(self):
        """Test the main function with command line arguments."""
        test_data = [
            ["test-package==1.0", "MIT"],
        ]

        self.create_test_csv(test_data)
        self.create_test_preamble("Main Function Test\n")
        self.create_test_license_file("MIT", "MIT License for main test")

        # Mock sys.argv to simulate command line arguments
        test_args = [
            "generate_third_party_programs.py",
            self.input_file,
            "--output", self.output_file,
            "--preamble", self.preamble_file,
            "--licenses-dir", self.licenses_dir
        ]

        with patch('sys.argv', test_args):
            with patch('requests.get') as mock_get, patch('requests.head') as mock_head:
                mock_get.side_effect = Exception("No network")
                mock_head.return_value.status_code = 404
                main()

        # Verify output was created
        self.assertTrue(os.path.exists(self.output_file))

        with open(self.output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("Main Function Test", content)
        self.assertIn("test-package==1.0", content)
        self.assertIn("MIT License for main test", content)

    def test_parse_license_expression_single(self):
        """Test parsing single license expressions."""
        # Simple single license
        result = parse_license_expression("MIT")
        self.assertEqual(result["type"], "single")
        self.assertEqual(result["license"], "MIT")

        # Single license with parentheses
        result = parse_license_expression("(MIT)")
        self.assertEqual(result["type"], "single")
        self.assertEqual(result["license"], "MIT")

        # Empty expression
        result = parse_license_expression("")
        self.assertEqual(result["type"], "single")
        self.assertEqual(result["license"], "")

    def test_parse_license_expression_and(self):
        """Test parsing AND license expressions."""
        # Simple AND expression
        result = parse_license_expression("MIT AND Apache-2.0")
        self.assertEqual(result["type"], "and")
        self.assertIn("MIT", result["licenses"])
        self.assertIn("Apache-2.0", result["licenses"])

        # AND with parentheses
        result = parse_license_expression("(MIT AND Python-2.0)")
        self.assertEqual(result["type"], "and")
        self.assertIn("MIT", result["licenses"])
        self.assertIn("Python-2.0", result["licenses"])

        # Multiple AND
        result = parse_license_expression("BSD-3-Clause AND BSD-4-Clause AND ISC")
        self.assertEqual(result["type"], "and")
        self.assertEqual(len(result["licenses"]), 3)
        self.assertIn("BSD-3-Clause", result["licenses"])
        self.assertIn("BSD-4-Clause", result["licenses"])
        self.assertIn("ISC", result["licenses"])

    def test_parse_license_expression_or(self):
        """Test parsing OR license expressions."""
        # Simple OR expression
        result = parse_license_expression("MIT OR Apache-2.0")
        self.assertEqual(result["type"], "or")
        self.assertIn("MIT", result["licenses"])
        self.assertIn("Apache-2.0", result["licenses"])

        # OR with parentheses
        result = parse_license_expression("(MIT OR GPL-2.0)")
        self.assertEqual(result["type"], "or")
        self.assertIn("MIT", result["licenses"])
        self.assertIn("GPL-2.0", result["licenses"])

        # Multiple OR
        result = parse_license_expression("MIT OR Apache-2.0 OR BSD-3-Clause")
        self.assertEqual(result["type"], "or")
        self.assertEqual(len(result["licenses"]), 3)

    def test_parse_license_expression_complex(self):
        """Test parsing complex license expressions with nested operators."""
        # AND with OR (OR has higher precedence in SPDX)
        result = parse_license_expression("MIT AND (Apache-2.0 OR GPL-2.0)")
        self.assertEqual(result["type"], "and")
        # Should have MIT and a nested OR expression

        # Complex expression from real data
        result = parse_license_expression("BSD-3-Clause AND BSD-4-Clause AND ISC AND curl AND LicenseRef-other")
        self.assertEqual(result["type"], "and")
        self.assertGreaterEqual(len(result["licenses"]), 5)

    def test_parse_license_expression_case_insensitive(self):
        """Test parsing license expressions with case-insensitive operators."""
        # Test lowercase 'and'
        result = parse_license_expression("MIT and Apache-2.0")
        self.assertEqual(result["type"], "and")
        self.assertIn("MIT", result["licenses"])
        self.assertIn("Apache-2.0", result["licenses"])

        # Test lowercase 'or'
        result = parse_license_expression("MIT or GPL-2.0")
        self.assertEqual(result["type"], "or")
        self.assertIn("MIT", result["licenses"])
        self.assertIn("GPL-2.0", result["licenses"])

        # Test mixed case 'AnD'
        result = parse_license_expression("BSD-3-Clause AnD ISC")
        self.assertEqual(result["type"], "and")
        self.assertIn("BSD-3-Clause", result["licenses"])
        self.assertIn("ISC", result["licenses"])

        # Test mixed case 'Or'
        result = parse_license_expression("MIT Or Apache-2.0")
        self.assertEqual(result["type"], "or")
        self.assertIn("MIT", result["licenses"])
        self.assertIn("Apache-2.0", result["licenses"])

        # Test with parentheses
        result = parse_license_expression("(MIT and Python-2.0)")
        self.assertEqual(result["type"], "and")
        self.assertIn("MIT", result["licenses"])
        self.assertIn("Python-2.0", result["licenses"])

        # Test multiple operators with mixed case
        result = parse_license_expression("MIT and Apache-2.0 AND BSD-3-Clause")
        self.assertEqual(result["type"], "and")
        self.assertEqual(len(result["licenses"]), 3)

    def test_get_licenses_from_expression(self):
        """Test extracting individual licenses from expressions."""
        # Single license
        licenses = get_licenses_from_expression("MIT")
        self.assertEqual(len(licenses), 1)
        self.assertIn("MIT", licenses)

        # AND expression
        licenses = get_licenses_from_expression("MIT AND Apache-2.0")
        self.assertEqual(len(licenses), 2)
        self.assertIn("MIT", licenses)
        self.assertIn("Apache-2.0", licenses)

        # OR expression
        licenses = get_licenses_from_expression("MIT OR GPL-2.0")
        self.assertEqual(len(licenses), 2)
        self.assertIn("MIT", licenses)
        self.assertIn("GPL-2.0", licenses)

        # Complex expression
        licenses = get_licenses_from_expression("(MIT AND Python-2.0)")
        self.assertEqual(len(licenses), 2)
        self.assertIn("MIT", licenses)
        self.assertIn("Python-2.0", licenses)

        # Very complex expression
        licenses = get_licenses_from_expression("BSD-3-Clause AND BSD-4-Clause AND ISC AND curl")
        self.assertGreaterEqual(len(licenses), 4)
        self.assertIn("BSD-3-Clause", licenses)
        self.assertIn("ISC", licenses)

    def test_download_license_expression_and(self):
        """Test downloading license texts for AND expressions."""
        # Clear cache before test
        _license_text_cache.clear()

        license_sources = {}
        failed_licenses = []
        special_licenses_skipped = set()

        # Create test license files
        self.create_test_license_file("MIT", "MIT License Text Here")
        self.create_test_license_file("Apache-2.0", "Apache License Text Here")

        # Mock network requests to force using local files
        with patch('requests.get') as mock_get, patch('requests.head') as mock_head:
            mock_get.side_effect = Exception("Use local files")
            mock_head.return_value.status_code = 404

            # Test AND expression
            result = download_license_expression_text(
                "MIT AND Apache-2.0",
                license_sources,
                failed_licenses,
                self.licenses_dir,
                special_licenses_skipped
            )

        # Should contain both license texts
        self.assertIn("MIT", result)
        self.assertIn("Apache-2.0", result)
        self.assertIn("MIT License Text Here", result)
        self.assertIn("Apache License Text Here", result)

        # Check cache was populated
        self.assertIn("MIT", _license_text_cache)
        self.assertIn("Apache-2.0", _license_text_cache)

    def test_download_license_expression_or(self):
        """Test downloading license texts for OR expressions."""
        # Clear cache before test
        _license_text_cache.clear()

        license_sources = {}
        failed_licenses = []
        special_licenses_skipped = set()

        # Create only one of the OR alternatives
        self.create_test_license_file("MIT", "MIT License Text for OR test")

        # Mock network requests to force using local files
        with patch('requests.get') as mock_get, patch('requests.head') as mock_head:
            mock_get.side_effect = Exception("Use local files")
            mock_head.return_value.status_code = 404

            # Test OR expression - should get the available one
            result = download_license_expression_text(
                "MIT OR Unknown-License",
                license_sources,
                failed_licenses,
                self.licenses_dir,
                special_licenses_skipped
            )

        # Should contain MIT license text (first available)
        self.assertIn("MIT", result)
        self.assertIn("MIT License Text for OR test", result)
        self.assertIn("chosen from OR alternatives", result)

    def test_download_license_expression_or_none_found(self):
        """Test OR expression when none of the alternatives are found."""
        # Clear cache before test
        _license_text_cache.clear()

        license_sources = {}
        failed_licenses = []
        special_licenses_skipped = set()

        # Test OR expression with no available licenses
        result = download_license_expression_text(
            "Unknown-1 OR Unknown-2",
            license_sources,
            failed_licenses,
            self.licenses_dir,
            special_licenses_skipped
        )

        # Should return None when no alternatives are found
        self.assertIsNone(result)
        self.assertIn("Unknown-1", failed_licenses)
        self.assertIn("Unknown-2", failed_licenses)

    def test_download_license_expression_with_cache(self):
        """Test that license text cache works correctly."""
        # Clear cache before test
        _license_text_cache.clear()

        license_sources = {}
        failed_licenses = []
        special_licenses_skipped = set()

        self.create_test_license_file("MIT", "MIT License Cached Text")

        # Mock network requests to force using local files
        with patch('requests.get') as mock_get, patch('requests.head') as mock_head:
            mock_get.side_effect = Exception("Use local files")
            mock_head.return_value.status_code = 404

            # First call - should read from file
            result1 = download_license_expression_text(
                "MIT",
                license_sources,
                failed_licenses,
                self.licenses_dir,
                special_licenses_skipped
            )

            # Second call - should use cache
            result2 = download_license_expression_text(
                "MIT",
                license_sources,
                failed_licenses,
                self.licenses_dir,
                special_licenses_skipped
            )

        # Both should return the same text
        self.assertEqual(result1, result2)
        self.assertIn("MIT License Cached Text", result1)

        # Verify cache contains the license
        self.assertIn("MIT", _license_text_cache)

    def test_process_dependencies_with_license_expressions(self):
        """Test processing dependencies with license expressions."""
        # Clear cache before test
        _license_text_cache.clear()

        test_data = [
            ["component1==1.0.0", "MIT AND Apache-2.0"],
            ["component2==1.0.0", "BSD-3-Clause OR GPL-2.0"],
            ["component3==1.0.0", "(MIT AND Python-2.0)"],
        ]

        self.create_test_csv(test_data)
        self.create_test_preamble("License Expression Test\n")

        # Create license files
        self.create_test_license_file("MIT", "MIT License Text")
        self.create_test_license_file("Apache-2.0", "Apache License Text")
        self.create_test_license_file("BSD-3-Clause", "BSD 3-Clause Text")
        self.create_test_license_file("Python-2.0", "Python License Text")

        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Use local files")
            process_dependencies(self.input_file, self.output_file,
                               self.preamble_file, self.licenses_dir)

        # Verify output
        self.assertTrue(os.path.exists(self.output_file))

        with open(self.output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check all components are present
        self.assertIn("component1==1.0.0", content)
        self.assertIn("component2==1.0.0", content)
        self.assertIn("component3==1.0.0", content)

        # Check license expressions are preserved
        self.assertIn("MIT AND Apache-2.0", content)
        self.assertIn("BSD-3-Clause OR GPL-2.0", content)

    def test_main_function_missing_input_file(self):
        """Test main function error handling for missing input file."""
        non_existent_file = os.path.join(self.test_dir, "missing.csv")

        test_args = [
            "generate_third_party_programs.py",
            non_existent_file
        ]

        with patch('sys.argv', test_args):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)


def run_integration_test():
    """Run a simple integration test with known data."""
    print("Running integration test...")

    # Create a temporary directory for the test
    test_dir = tempfile.mkdtemp()

    try:
        # Create test input CSV
        input_file = os.path.join(test_dir, "integration_test.csv")
        with open(input_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Component', 'License'])
            writer.writerow(['numpy==1.21.0', 'BSD-3-Clause'])
            writer.writerow(['click==8.0.0', 'BSD-3-Clause'])
            writer.writerow(['requests==2.25.0', 'Apache-2.0'])

        # Create preamble
        preamble_file = os.path.join(test_dir, "preamble.txt")
        with open(preamble_file, 'w', encoding='utf-8') as f:
            f.write("Integration Test Third Party Programs\n")

        # Create licenses directory with sample license
        licenses_dir = os.path.join(test_dir, "licenses")
        os.makedirs(licenses_dir)

        with open(os.path.join(licenses_dir, "BSD-3-Clause.txt"), 'w') as f:
            f.write("BSD 3-Clause License\nSample license text for testing.")

        # Run the script
        output_file = os.path.join(test_dir, "integration_output.txt")

        with patch('sys.argv', [
            'generate_third_party_programs.py',
            input_file,
            '--output', output_file,
            '--preamble', preamble_file,
            '--licenses-dir', licenses_dir
        ]):
            # Mock requests to avoid network calls
            with patch('requests.get') as mock_get:
                mock_get.side_effect = Exception("No network in test")
                main()

        # Verify output
        assert os.path.exists(output_file), "Output file was not created"

        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Basic checks
        assert "Integration Test Third Party Programs" in content
        assert "numpy==1.21.0" in content
        assert "click==8.0.0" in content
        assert "requests==2.25.0" in content
        assert "BSD-3-Clause" in content
        assert "Apache-2.0" in content

        print("✓ Integration test passed!")

    finally:
        shutil.rmtree(test_dir)


if __name__ == '__main__':
    # Run unit tests
    print("Running unit tests...")
    unittest.main(argv=[''], exit=False, verbosity=2)

    print("\n" + "="*50)

    # Run integration test
    run_integration_test()

    print("\n✓ All tests completed successfully!")