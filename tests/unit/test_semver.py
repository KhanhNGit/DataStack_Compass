
from processing.spark_utils.semver import (
    parse_semver,
    compare_semver,
    sort_versions,
    is_version_affected
)

def test_parse_semver():
    assert parse_semver("3.6.1-rc.2") == (3, 6, 1, "rc.2")
    assert parse_semver("v3.6.1") == (3, 6, 1, "")
    assert parse_semver("3.6") == (3, 6, 0, "")
    assert parse_semver("3") == (3, 0, 0, "")
    assert parse_semver("1.0.0-alpha.1+build.123") == (1, 0, 0, "alpha.1")
    assert parse_semver("not_a_version") == (0, 0, 0, "")

def test_compare_semver():
    # Basic
    assert compare_semver("1.0.0", "1.0.0") == 0
    assert compare_semver("2.0.0", "1.0.0") == 1
    assert compare_semver("1.0.0", "2.0.0") == -1
    
    # Minor and Patch
    assert compare_semver("1.1.0", "1.0.0") == 1
    assert compare_semver("1.0.1", "1.0.0") == 1
    
    # Pre-release
    assert compare_semver("1.0.0-alpha", "1.0.0") == -1
    assert compare_semver("1.0.0-alpha", "1.0.0-beta") == -1
    assert compare_semver("1.0.0-alpha.1", "1.0.0-alpha.2") == -1
    assert compare_semver("1.0.0-beta.2", "1.0.0-beta.11") == -1 # 2 < 11
    assert compare_semver("1.0.0-rc.1", "1.0.0-rc.1") == 0
    
    # Partial versions
    assert compare_semver("3.6", "3.6.0") == 0
    assert compare_semver("v3.6", "3.6") == 0

def test_sort_versions():
    versions = ["1.0.0-alpha", "1.0.0", "0.9.0", "1.1.0", "1.0.0-beta"]
    
    # Descending (Latest first)
    assert sort_versions(versions) == [
        "1.1.0",
        "1.0.0",
        "1.0.0-beta",
        "1.0.0-alpha",
        "0.9.0"
    ]
    
    # Ascending
    assert sort_versions(versions, reverse=False) == [
        "0.9.0",
        "1.0.0-alpha",
        "1.0.0-beta",
        "1.0.0",
        "1.1.0"
    ]

def test_is_version_affected():
    # Exact
    assert is_version_affected("3.5.0", "= 3.5.0") is True
    assert is_version_affected("3.5.0", "3.5.0") is True
    assert is_version_affected("3.5.1", "= 3.5.0") is False
    
    # Operators
    assert is_version_affected("3.5.0", "<= 3.5.0") is True
    assert is_version_affected("3.5.1", "<= 3.5.0") is False
    assert is_version_affected("3.5.0", "< 3.6.0") is True
    assert is_version_affected("3.6.0", "> 3.5.0") is True
    assert is_version_affected("3.5.0", ">= 3.0.0") is True
    
    # Ranges
    assert is_version_affected("3.5.0", ">= 3.0.0, < 3.6.0") is True
    assert is_version_affected("3.6.0", ">= 3.0.0, < 3.6.0") is False
    assert is_version_affected("2.9.0", ">= 3.0.0, < 3.6.0") is False
    
    # Wildcards
    assert is_version_affected("3.4.1", "3.4.x") is True
    assert is_version_affected("3.5.0", "3.4.x") is False
    assert is_version_affected("3.4.1-rc.1", "3.4.*") is True
    
    # Wildcard prefix
    assert is_version_affected("3.4.5", "3.x") is True
    assert is_version_affected("4.0.0", "3.x") is False
    
    # Any
    assert is_version_affected("3.4.5", "*") is True
    assert is_version_affected("1.0.0", "") is True
