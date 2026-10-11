"""The CI gate must reject skipped, empty, or unsuccessful test reports."""
import importlib.util
from pathlib import Path

import pytest


REPORT_CHECKER = Path(__file__).resolve().parents[3] / 'scripts/check-agent-test-report.py'
spec = importlib.util.spec_from_file_location('agent_test_report', REPORT_CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.mark.parametrize('body,expected', [
    ('<testcase name="passes"/>', 0),
    ('', 1),
    ('<testcase name="fails"><failure/></testcase>', 1),
    ('<testcase name="error"><error/></testcase>', 1),
    ('<testcase name="skipped"><skipped/></testcase>', 1),
    ('<testcase name="passes"/><testcase name="skipped"><skipped/></testcase>', 1),
])
def test_report_gate(tmp_path, body, expected):
    report = tmp_path / 'report.xml'
    report.write_text(f'<testsuites><testsuite>{body}</testsuite></testsuites>', encoding='utf-8')
    assert checker.check_report(report) == expected


def test_missing_or_malformed_report_cannot_pass(tmp_path):
    with pytest.raises(FileNotFoundError):
        checker.check_report(tmp_path / 'missing.xml')
    report = tmp_path / 'bad.xml'
    report.write_text('<invalid', encoding='utf-8')
    with pytest.raises(checker.ElementTree.ParseError):
        checker.check_report(report)
