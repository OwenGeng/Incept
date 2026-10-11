"""Fail the Agent acceptance gate on empty, failed or skipped JUnit tests."""
import sys
from pathlib import Path
from xml.etree import ElementTree


def check_report(path: Path) -> int:
    root = ElementTree.parse(path).getroot()
    cases = list(root.iter('testcase'))
    violations = sum(any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped'))
                     for case in cases)
    if not cases or violations:
        print(f'Agent acceptance blocked: {len(cases)} cases, {violations} failed/error/skipped cases.')
        return 1
    print(f'Agent acceptance passed: {len(cases)} cases; zero failures, errors or skips.')
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python scripts/check-agent-test-report.py REPORT.xml')
    raise SystemExit(check_report(Path(sys.argv[1])))
