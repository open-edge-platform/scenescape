"""
Test Category Mapping for Zephyr Scale

Maps test ID prefixes to Zephyr Scale test metadata:
- Test Category
- Test Type
- Component

The first matching prefix is used, so order matters.
Put more specific prefixes before more general ones.

Environment Variables:
    TEST_CATEGORY_PREFIX: Default test ID prefix (default: Vision_AI)
    TEST_CATEGORY_CONFIG: Path to category config file (default: test_category_config.yaml)
"""

import os
import logging
from typing import Tuple, List

try:
    import yaml
except ImportError as exc:
    raise ImportError(
        "PyYAML is required for config-driven test categories. "
        "Install with: pip install pyyaml"
    ) from exc


TEST_PREFIX = os.getenv("TEST_CATEGORY_PREFIX", "Vision_AI")
CONFIG_PATH = os.getenv("TEST_CATEGORY_CONFIG", "test_category_config.yaml")

logger = logging.getLogger(__name__)



# Config loader
def _load_test_categories() -> dict:
    """
    Load test category mappings from YAML config.

    Returns:
        dict: {full_prefix: (category, type, component)}
    """
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(
            f"Test category config file not found: {CONFIG_PATH}"
        )

    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f) or {}

    categories = {}

    for entry in config.get("categories", []):
        # Required keys (fail fast)
        for key in ("prefix", "category", "type", "component"):
            if key not in entry:
                raise ValueError(
                    f"Missing '{key}' in test category config entry: {entry}"
                )

        full_prefix = f"{TEST_PREFIX}{entry['prefix']}"

        categories[full_prefix] = (
            entry["category"],
            entry["type"],
            entry["component"],
        )

    if not categories:
        raise ValueError("No test categories loaded from config")

    return categories


# Category mappings (CONFIG-DRIVEN)
test_categories = _load_test_categories()


def summary_to_test_category(summary: str) -> Tuple[str, str, str]:
    """
    Extract test category, type, and component from test summary/ID.

    Args:
        summary: Test case summary
                 (e.g., "Vision_AI/API/001: Test login")

    Returns:
        Tuple of (category, type, component) or ('', '', '') if no match
    """
    for prefix, (category, type_, component) in test_categories.items():
        if summary.startswith(prefix):
            return category, type_, component

    # No match found
    return "", "", ""


def get_available_categories() -> List[Tuple[str, str, str, str]]:
    """
    Get list of available test categories.

    Returns:
        List of (prefix, category, type, component) tuples
    """
    return [
        (prefix, cat, type_, comp)
        for prefix, (cat, type_, comp) in test_categories.items()
    ]


def add_custom_category(prefix: str, category: str, type_: str, component: str) -> None:
    """
    Add a custom category mapping at runtime.

    Args:
        prefix: Test ID prefix (e.g., "Vision_AI/CUSTOM/")
        category: Category name
        type_: Type name
        component: Component name
    """
    test_categories[prefix] = (category, type_, component)


def validate_summary(summary: str) -> bool:
    """
    Check if a summary has a recognized category prefix.

    Args:
        summary: Test case summary

    Returns:
        True if summary matches a known category
    """
    category, type_, component = summary_to_test_category(summary)
    return bool(category and type_ and component)



# Debug logging
if __name__ != "__main__":
    logger.info(
        "Test categories loaded with prefix '%s' (%d categories)",
        TEST_PREFIX,
        len(test_categories),
    )
    logger.debug("Available category prefixes: %s", list(test_categories.keys()))


# Example usage / local testing
if __name__ == "__main__":
    print("Test Category Mapper")
    print("=" * 60)
    print(f"Configured prefix: {TEST_PREFIX}")
    print(f"Config file: {CONFIG_PATH}")
    print(f"Available categories: {len(test_categories)}\n")

    print("Mappings:")
    for prefix, (cat, type_, comp) in test_categories.items():
        print(f"  {prefix:25} → {cat:20} / {type_:12} / {comp}")
    print()

    test_cases = [
        "Vision_AI/API/001: Test login",
        "Vision_AI/INT/042: Verify integration",
        "Vision_AI/UI/005: Check UI",
        "UNKNOWN/TEST/001: Should not match",
    ]

    print("Test Examples:")
    for test in test_cases:
        cat, type_, comp = summary_to_test_category(test)
        status = "✅" if cat else "❌"
        print(f"  {status} {test}")
        if cat:
            print(f"      → Category: {cat}, Type: {type_}, Component: {comp}")
        else:
            print("      → No category found")
