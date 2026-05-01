# tests/test_governance.py

import pytest
from datetime import date
from modules.governance.ethics_auditor import EthicsAuditor, AuditResult
from modules.governance.ethics_audit_runner import (
    CheckResult, ComplianceReport, format_text_report, format_json_report
)


@pytest.fixture
def auditor():
    return EthicsAuditor(llm_client=None)


# ── EthicsAuditor unit tests ──────────────────────────────────────────────────

VALID_OUTPUT = """
## Meeting Minutes
**Network:** VASTN
**Date:** 2024-11-15
**Attendees:** Dr. Minh (HCMUT), Prof. Sarah (NUS)

### Agenda Items Discussed
The team reviewed the AI module update timeline.

### Decisions Made
The module will be updated before next semester.

### Action Items
| Owner | Deadline | Description |
|---|---|---|
| Prof. Sarah | 2024-12-20 | Draft updated module outline |

### Next Meeting
2025-01-25

---
*This document was generated with AI assistance and is pending human review.*
"""


def test_valid_output_passes(auditor):
    result = auditor.evaluate(VALID_OUTPUT, "meeting_minutes_v1", "en",
                              min_words=50, max_words=800)
    assert result.passed is True
    assert result.failed_checks == []


def test_missing_disclosure_fails(auditor):
    output_without_disclosure = VALID_OUTPUT.replace(
        "*This document was generated with AI assistance and is pending human review.*",
        ""
    )
    result = auditor.evaluate(output_without_disclosure,
                              "meeting_minutes_v1", "en")
    assert result.passed is False
    assert any("EC-07" in f for f in result.failed_checks)


def test_contact_info_fails(auditor):
    output_with_email = VALID_OUTPUT + "\nContact: sarah.chen@nus.edu.sg"
    result = auditor.evaluate(output_with_email, "meeting_minutes_v1", "en")
    assert result.passed is False
    assert any("EC-06" in f for f in result.failed_checks)


def test_output_too_short_gives_warning(auditor):
    short_output = (
        "Meeting happened. Done.\n\n"
        "*This document was generated with AI assistance.*"
    )
    result = auditor.evaluate(short_output, "meeting_minutes_v1", "en",
                              min_words=150, max_words=800)
    # EC-03 is a warning, not a blocker → should still pass
    assert result.passed is True
    assert any("EC-03" in w for w in result.warnings)


def test_wrong_language_gives_warning(auditor):
    # Vietnamese text but language='en'
    vi_output = (
        "Cuộc họp đã diễn ra tốt đẹp. Các quyết định đã được thông qua.\n\n"
        "*This document was generated with AI assistance and is pending human review.*"
    )
    result = auditor.evaluate(vi_output, "meeting_minutes_v1", "en")
    assert result.passed is True
    assert any("EC-04" in w for w in result.warnings)


# ── ComplianceReport unit tests ───────────────────────────────────────────────

def make_result(passed: bool, task_type="meeting_minutes",
                language="en", consequence_level="high",
                failed_checks=None):
    return CheckResult(
        log_id="test-log-id",
        task_type=task_type,
        template_name=f"{task_type}_v1",
        language=language,
        consequence_level=consequence_level,
        created_at=date(2024, 1, 1),
        passed=passed,
        failed_checks=failed_checks or [],
        warnings=[],
    )


def test_compliance_rate_all_pass():
    results = [make_result(True) for _ in range(10)]
    report = ComplianceReport(date(2024, 1, 1), date(2024, 12, 31), results)
    assert report.compliance_rate == 100.0


def test_compliance_rate_partial():
    results = (
        [make_result(True) for _ in range(95)]
        + [make_result(False, failed_checks=["EC-07: missing disclosure"])
           for _ in range(5)]
    )
    report = ComplianceReport(date(2024, 1, 1), date(2024, 12, 31), results)
    assert report.compliance_rate == pytest.approx(95.0)


def test_compliance_rate_empty():
    report = ComplianceReport(date(2024, 1, 1), date(2024, 12, 31), [])
    assert report.compliance_rate == 100.0


def test_by_task_type_breakdown():
    results = [
        make_result(True,  task_type="meeting_minutes"),
        make_result(True,  task_type="meeting_minutes"),
        make_result(False, task_type="meeting_minutes",
                    failed_checks=["EC-07"]),
        make_result(True,  task_type="summarization"),
    ]
    report = ComplianceReport(date(2024, 1, 1), date(2024, 12, 31), results)
    breakdown = report.by_task_type
    assert breakdown["meeting_minutes"]["total"] == 3
    assert breakdown["meeting_minutes"]["passed"] == 2
    assert breakdown["meeting_minutes"]["rate"] == pytest.approx(66.67, rel=1e-2)
    assert breakdown["summarization"]["rate"] == 100.0


def test_failure_frequency():
    results = [
        make_result(False, failed_checks=["EC-07: missing", "EC-06: email found"]),
        make_result(False, failed_checks=["EC-07: missing"]),
        make_result(True),
    ]
    report = ComplianceReport(date(2024, 1, 1), date(2024, 12, 31), results)
    freq = report.failure_frequency
    assert freq.get("EC-07") == 2
    assert freq.get("EC-06") == 1


def test_high_consequence_failures():
    results = [
        make_result(False, consequence_level="high",
                    failed_checks=["EC-07"]),
        make_result(False, consequence_level="medium",
                    failed_checks=["EC-07"]),
        make_result(True,  consequence_level="high"),
    ]
    report = ComplianceReport(date(2024, 1, 1), date(2024, 12, 31), results)
    hcf = report.high_consequence_failures
    assert len(hcf) == 1
    assert hcf[0].consequence_level == "high"


def test_text_report_renders(auditor):
    results = [make_result(True) for _ in range(5)]
    report = ComplianceReport(date(2024, 1, 1), date(2024, 12, 31), results)
    text = format_text_report(report)
    assert "ETHICS COMPLIANCE REPORT" in text
    assert "100.00%" in text
    assert "MEETING TARGET" in text


def test_json_report_is_valid_json():
    import json
    results = [make_result(True) for _ in range(3)]
    report = ComplianceReport(date(2024, 1, 1), date(2024, 12, 31), results)
    json_str = format_json_report(report)
    parsed = json.loads(json_str)
    assert parsed["summary"]["total"] == 3
    assert parsed["summary"]["compliance_rate"] == 100.0