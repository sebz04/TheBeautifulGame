import pytest
from check_licenses import find_violations, is_allowed


@pytest.mark.parametrize(
    "license_text",
    [
        "MIT",
        "MIT License",
        "BSD License",
        "BSD-3-Clause",
        "Apache Software License",
        "Apache-2.0",
        "Python Software Foundation License",
        "PSF-2.0",
        "ISC License (ISCL)",
        "Mozilla Public License 2.0 (MPL 2.0)",
    ],
)
def test_permissive_licenses_allowed(license_text):
    assert is_allowed(license_text)


@pytest.mark.parametrize(
    "license_text",
    ["GNU General Public License v3 (GPLv3)", "AGPL-3.0", "UNKNOWN", "", "Proprietary"],
)
def test_copyleft_and_unknown_rejected(license_text):
    assert not is_allowed(license_text)


def test_or_expression_needs_one_allowed_option():
    assert is_allowed("GPL-3.0 OR MIT")
    assert is_allowed("MIT License; GNU General Public License v2 (GPLv2)")


def test_and_expression_needs_every_part_allowed():
    assert not is_allowed("MIT AND GPL-3.0")
    assert is_allowed("MIT AND Apache-2.0")


def test_only_runtime_packages_are_checked():
    packages = [
        {"Name": "pytest-gpl-plugin", "License": "GPL-3.0"},
        {"Name": "pydantic", "License": "MIT"},
    ]
    assert find_violations(packages, runtime={"pydantic"}) == []


def test_violation_reported_with_name_and_license():
    packages = [{"Name": "Bad_Pkg", "License": "GPL-3.0"}]
    assert find_violations(packages, runtime={"bad-pkg"}) == ["Bad_Pkg: GPL-3.0"]


def test_runtime_package_missing_from_report_is_a_violation():
    assert find_violations([], runtime={"pydantic"}) == ["pydantic: not found in license report"]


def test_numpy_style_compound_permissive_expression_allowed():
    assert is_allowed("BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0")


def test_packages_for_other_platforms_are_skipped():
    from check_licenses import parse_export

    export = "\n".join([
        "# generated",
        "pydantic==2.9.0",
        "pywin32==311 ; sys_platform == 'win32'",
        "uvloop==0.21 ; sys_platform != 'win32'",
        "    # via mcp",
    ])  # fmt: skip
    names = parse_export(export, {"sys_platform": "darwin"})
    assert names == {"pydantic", "uvloop"}
    assert "pywin32" in parse_export(export, {"sys_platform": "win32"})
