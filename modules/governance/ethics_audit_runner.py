# modules/governance/ethics_audit_runner.py
"""
Standalone ethics audit runner.
Evaluates all unaudited log entries against the ethics checklist
and writes a structured compliance report.

Usage:
    python -m modules.governance.ethics_audit_runner
    python -m modules.governance.ethics_audit_runner --period 2024-01-01 2024-12-31
    python -m modules.governance.ethics_audit_runner --format json
"""

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from sqlalchemy import text
from modules.analytics.db_connector import get_session
from modules.governance.ethics_auditor import EthicsAuditor


# ── Report data structures ────────────────────────────────────────────────────

class CheckResult:
    def __init__(self, log_id, task_type, template_name, language,
                 consequence_level, created_at, passed, failed_checks, warnings):
        self.log_id = log_id
        self.task_type = task_type
        self.template_name = template_name
        self.language = language
        self.consequence_level = consequence_level
        self.created_at = created_at
        self.passed = passed
        self.failed_checks = failed_checks
        self.warnings = warnings


class ComplianceReport:
    def __init__(self, period_start, period_end, results: list[CheckResult]):
        self.period_start = period_start
        self.period_end = period_end
        self.results = results
        self.generated_at = datetime.now(timezone.utc)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def compliance_rate(self) -> float:
        return (self.passed / self.total * 100) if self.total > 0 else 100.0

    @property
    def by_task_type(self) -> dict:
        """Compliance rate broken down by task type."""
        groups = {}
        for r in self.results:
            if r.task_type not in groups:
                groups[r.task_type] = {"total": 0, "passed": 0}
            groups[r.task_type]["total"] += 1
            if r.passed:
                groups[r.task_type]["passed"] += 1
        return {
            k: {
                "total": v["total"],
                "passed": v["passed"],
                "rate": round(v["passed"] / v["total"] * 100, 2)
                        if v["total"] > 0 else 100.0,
            }
            for k, v in groups.items()
        }

    @property
    def by_language(self) -> dict:
        """Compliance rate broken down by output language."""
        groups = {}
        for r in self.results:
            lang = r.language or "unknown"
            if lang not in groups:
                groups[lang] = {"total": 0, "passed": 0}
            groups[lang]["total"] += 1
            if r.passed:
                groups[lang]["passed"] += 1
        return {
            k: {
                "total": v["total"],
                "passed": v["passed"],
                "rate": round(v["passed"] / v["total"] * 100, 2)
                        if v["total"] > 0 else 100.0,
            }
            for k, v in groups.items()
        }

    @property
    def failure_frequency(self) -> dict:
        """How often each check ID appears in failed_checks."""
        freq = {}
        for r in self.results:
            for check in r.failed_checks:
                check_id = check.split(":")[0].strip()
                freq[check_id] = freq.get(check_id, 0) + 1
        return dict(sorted(freq.items(), key=lambda x: -x[1]))

    @property
    def high_consequence_failures(self) -> list[CheckResult]:
        return [
            r for r in self.results
            if not r.passed and r.consequence_level == "high"
        ]


# ── Audit runner ──────────────────────────────────────────────────────────────

class EthicsAuditRunner:
    """
    Fetches log entries from the database, runs the ethics checklist
    on each output, and produces a ComplianceReport.
    """

    def __init__(self):
        self.auditor = EthicsAuditor(llm_client=None)
        # LLM client intentionally omitted for batch runs:
        # EC-01 and EC-02 (LLM-assisted) are skipped to keep
        # batch audits fast and cost-free. They run in real-time
        # during the orchestrator flow instead.

    def run(
        self,
        period_start: date,
        period_end: date,
    ) -> ComplianceReport:
        with get_session() as session:
            rows = session.execute(text("""
                SELECT
                    log_id, task_type, template_name, language,
                    consequence_level, output_text, created_at
                FROM audit_logs
                WHERE created_at BETWEEN :start AND :end
                ORDER BY created_at ASC
            """), {
                "start": period_start,
                "end": period_end,
            }).fetchall()

        results = []
        for row in rows:
            result = self.auditor.evaluate(
                output_text=row.output_text or "",
                template_id=row.template_name,
                language=row.language or "en",
            )
            results.append(CheckResult(
                log_id=row.log_id,
                task_type=row.task_type,
                template_name=row.template_name,
                language=row.language,
                consequence_level=row.consequence_level,
                created_at=row.created_at,
                passed=result.passed,
                failed_checks=result.failed_checks,
                warnings=result.warnings,
            ))

        report = ComplianceReport(period_start, period_end, results)

        # Write K10 back to kpi_values
        self._update_k10(report)

        return report

    def _update_k10(self, report: ComplianceReport) -> None:
        """Write the computed ethics compliance rate to kpi_values."""
        with get_session() as session:
            session.execute(text("""
                INSERT INTO kpi_values
                    (kpi_id, scope_type, scope_id, period_start,
                     period_end, value, computed_at)
                VALUES
                    ('K10', 'network', 1, :start, :end, :value, :now)
            """), {
                "start": report.period_start,
                "end": report.period_end,
                "value": round(report.compliance_rate, 4),
                "now": report.generated_at,
            })
            session.commit()


# ── Report formatters ─────────────────────────────────────────────────────────

def format_text_report(report: ComplianceReport) -> str:
    """Render a human-readable compliance report."""
    sep = "=" * 70
    lines = [
        sep,
        "ETHICS COMPLIANCE REPORT",
        f"EdNet AI-Enabled Framework — Audit Run",
        sep,
        f"Period          : {report.period_start}  →  {report.period_end}",
        f"Generated at    : {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "── SUMMARY ─────────────────────────────────────────────────────────",
        f"Total entries evaluated   : {report.total}",
        f"Passed                    : {report.passed}",
        f"Failed                    : {report.failed}",
        f"Compliance rate           : {report.compliance_rate:.2f}%",
        f"Target                    : ≥ 95.00%",
        f"Status                    : "
        f"{'✅ MEETING TARGET' if report.compliance_rate >= 95.0 else '⚠️  BELOW TARGET'}",
        "",
        "── BREAKDOWN BY TASK TYPE ───────────────────────────────────────────",
    ]

    for task, stats in report.by_task_type.items():
        flag = "✅" if stats["rate"] >= 95.0 else "⚠️ "
        lines.append(
            f"  {flag} {task:<35} "
            f"{stats['passed']}/{stats['total']}  ({stats['rate']:.1f}%)"
        )

    lines += [
        "",
        "── BREAKDOWN BY LANGUAGE ────────────────────────────────────────────",
    ]
    for lang, stats in report.by_language.items():
        flag = "✅" if stats["rate"] >= 95.0 else "⚠️ "
        lines.append(
            f"  {flag} {lang.upper():<8} "
            f"{stats['passed']}/{stats['total']}  ({stats['rate']:.1f}%)"
        )

    lines += [
        "",
        "── MOST FREQUENT FAILURES ───────────────────────────────────────────",
    ]
    if report.failure_frequency:
        for check_id, count in report.failure_frequency.items():
            lines.append(f"  {check_id:<8} : {count} occurrence(s)")
    else:
        lines.append("  None — all checks passed.")

    if report.high_consequence_failures:
        lines += [
            "",
            "── HIGH-CONSEQUENCE FAILURES (require immediate review) ─────────────",
        ]
        for r in report.high_consequence_failures:
            lines.append(f"  Log ID : {r.log_id}")
            lines.append(f"  Task   : {r.task_type}  |  Language: {r.language}")
            lines.append(f"  Failed : {'; '.join(r.failed_checks)}")
            lines.append("")

    lines.append(sep)
    return "\n".join(lines)


def format_json_report(report: ComplianceReport) -> str:
    """Render a machine-readable compliance report."""
    payload = {
        "period_start": str(report.period_start),
        "period_end": str(report.period_end),
        "generated_at": report.generated_at.isoformat(),
        "summary": {
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "compliance_rate": round(report.compliance_rate, 4),
            "target": 95.0,
            "meeting_target": report.compliance_rate >= 95.0,
        },
        "breakdown_by_task_type": report.by_task_type,
        "breakdown_by_language": report.by_language,
        "failure_frequency": report.failure_frequency,
        "high_consequence_failures": [
            {
                "log_id": r.log_id,
                "task_type": r.task_type,
                "language": r.language,
                "consequence_level": r.consequence_level,
                "failed_checks": r.failed_checks,
                "created_at": str(r.created_at),
            }
            for r in report.high_consequence_failures
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run ethics audit on EdNet audit logs."
    )
    parser.add_argument(
        "--period", nargs=2, metavar=("START", "END"),
        default=["2023-01-01", "2024-12-31"],
        help="Audit period as YYYY-MM-DD YYYY-MM-DD",
    )
    parser.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--output", metavar="FILE", default=None,
        help="Write report to file instead of stdout",
    )
    args = parser.parse_args()

    period_start = date.fromisoformat(args.period[0])
    period_end = date.fromisoformat(args.period[1])

    runner = EthicsAuditRunner()
    report = runner.run(period_start, period_end)

    if args.format == "json":
        content = format_json_report(report)
    else:
        content = format_text_report(report)

    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
        print(f"Report written to: {args.output}")
    else:
        print(content)


if __name__ == "__main__":
    main()