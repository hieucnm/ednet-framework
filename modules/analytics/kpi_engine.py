# modules/analytics/kpi_engine.py

from datetime import date, datetime, timezone
from sqlalchemy import text
from modules.analytics.db_connector import get_session


class KPIEngine:
    """
    Computes all KPIs defined in kpi_definitions and writes results
    to kpi_values. Each KPI has a dedicated method for clarity and
    independent testability.
    """

    def compute_all(
        self,
        network_id: int = 1,
        period_start: date = date(2023, 1, 1),
        period_end: date = date(2024, 12, 31),
    ) -> dict[str, float]:
        """
        Compute all 10 KPIs for the given network and period.
        Returns a dict of {kpi_id: value} for reporting.
        """
        print(f"Computing KPIs for network {network_id} "
              f"({period_start} → {period_end})...")

        results = {}
        methods = [
            ("K01", self.k01_participation_rate),
            ("K02", self.k02_collaboration_index),
            ("K03", self.k03_student_mobility_rate),
            ("K04", self.k04_joint_event_frequency),
            ("K05", self.k05_program_completion_rate),
            ("K06", self.k06_withdrawal_rate),
            ("K07", self.k07_multilingual_coverage),
            ("K08", self.k08_member_growth_rate),
            ("K09", self.k09_hitl_turnaround),
            ("K10", self.k10_ethics_compliance_rate),
        ]

        with get_session() as session:
            for kpi_id, method in methods:
                try:
                    value = method(session, network_id, period_start, period_end)
                    self._write(session, kpi_id, network_id, period_start,
                                period_end, value)
                    results[kpi_id] = round(value, 4)
                    print(f"  {kpi_id}: {value:.4f}")
                except Exception as e:
                    print(f"  {kpi_id}: ERROR — {e}")
                    results[kpi_id] = None
            session.commit()

        return results

    # ── K01: Network Participation Rate ──────────────────────────────────────

    def k01_participation_rate(
        self, session, network_id, period_start, period_end
    ) -> float:
        total = session.execute(text("""
            SELECT COUNT(*) FROM network_memberships
            WHERE network_id = :nid
        """), {"nid": network_id}).scalar() or 0

        active = session.execute(text("""
            SELECT COUNT(DISTINCT host_institution_id) FROM programs
            WHERE network_id = :nid
              AND status IN ('active', 'completed')
              AND start_date <= :end AND end_date >= :start
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).scalar() or 0

        return (active / total * 100) if total > 0 else 0.0

    # ── K02: Inter-institutional Collaboration Index ──────────────────────────

    def k02_collaboration_index(
        self, session, network_id, period_start, period_end
    ) -> float:
        n = session.execute(text("""
            SELECT COUNT(*) FROM network_memberships WHERE network_id = :nid
        """), {"nid": network_id}).scalar() or 0

        total_possible_pairs = n * (n - 1) / 2
        if total_possible_pairs == 0:
            return 0.0

        # Pairs from shared program hosting
        program_pairs = session.execute(text("""
            SELECT DISTINCT
                LEAST(p.host_institution_id, pp.institution_id),
                GREATEST(p.host_institution_id, pp.institution_id)
            FROM programs p
            JOIN program_partners pp ON p.program_id = pp.program_id
            WHERE p.network_id = :nid
              AND p.start_date <= :end AND p.end_date >= :start
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).fetchall()

        # Pairs from shared event participation
        event_pairs = session.execute(text("""
            SELECT DISTINCT
                LEAST(ep1.institution_id, ep2.institution_id),
                GREATEST(ep1.institution_id, ep2.institution_id)
            FROM event_participants ep1
            JOIN event_participants ep2
                ON ep1.event_id = ep2.event_id
               AND ep1.institution_id < ep2.institution_id
            JOIN events e ON ep1.event_id = e.event_id
            WHERE e.network_id = :nid
              AND e.event_date BETWEEN :start AND :end
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).fetchall()

        unique_pairs = set(program_pairs) | set(event_pairs)
        return len(unique_pairs) / total_possible_pairs * 100

    # ── K03: Student Mobility Rate ────────────────────────────────────────────

    def k03_student_mobility_rate(
        self, session, network_id, period_start, period_end
    ) -> float:
        total_enrolled = session.execute(text("""
            SELECT COUNT(DISTINCT e.student_id)
            FROM enrollments e
            JOIN programs p ON e.program_id = p.program_id
            WHERE p.network_id = :nid
              AND e.enrolled_date BETWEEN :start AND :end
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).scalar() or 0

        mobile = session.execute(text("""
            SELECT COUNT(DISTINCT mr.person_id)
            FROM mobility_records mr
            JOIN programs p ON mr.program_id = p.program_id
            WHERE mr.person_type = 'student'
              AND p.network_id = :nid
              AND mr.start_date BETWEEN :start AND :end
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).scalar() or 0

        return (mobile / total_enrolled * 100) if total_enrolled > 0 else 0.0

    # ── K04: Joint Event Frequency ────────────────────────────────────────────

    def k04_joint_event_frequency(
        self, session, network_id, period_start, period_end
    ) -> float:
        count = session.execute(text("""
            SELECT COUNT(DISTINCT e.event_id)
            FROM events e
            JOIN event_participants ep ON e.event_id = ep.event_id
            WHERE e.network_id = :nid
              AND e.event_date BETWEEN :start AND :end
            GROUP BY e.event_id
            HAVING COUNT(DISTINCT ep.institution_id) >= 2
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).rowcount

        return float(count)

    # ── K05: Program Completion Rate ──────────────────────────────────────────

    def k05_program_completion_rate(
        self, session, network_id, period_start, period_end
    ) -> float:
        total = session.execute(text("""
            SELECT COUNT(*) FROM enrollments e
            JOIN programs p ON e.program_id = p.program_id
            WHERE p.network_id = :nid
              AND e.enrolled_date BETWEEN :start AND :end
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).scalar() or 0

        passed = session.execute(text("""
            SELECT COUNT(*) FROM enrollments e
            JOIN programs p ON e.program_id = p.program_id
            WHERE p.network_id = :nid
              AND e.outcome = 'pass'
              AND e.enrolled_date BETWEEN :start AND :end
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).scalar() or 0

        return (passed / total * 100) if total > 0 else 0.0

    # ── K06: Student Withdrawal Rate ──────────────────────────────────────────

    def k06_withdrawal_rate(
        self, session, network_id, period_start, period_end
    ) -> float:
        total = session.execute(text("""
            SELECT COUNT(*) FROM enrollments e
            JOIN programs p ON e.program_id = p.program_id
            WHERE p.network_id = :nid
              AND e.enrolled_date BETWEEN :start AND :end
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).scalar() or 0

        withdrawn = session.execute(text("""
            SELECT COUNT(*) FROM enrollments e
            JOIN programs p ON e.program_id = p.program_id
            WHERE p.network_id = :nid
              AND e.status = 'withdrawn'
              AND e.enrolled_date BETWEEN :start AND :end
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).scalar() or 0

        return (withdrawn / total * 100) if total > 0 else 0.0

    # ── K07: Multilingual Program Coverage ───────────────────────────────────

    def k07_multilingual_coverage(
        self, session, network_id, period_start, period_end
    ) -> float:
        total = session.execute(text("""
            SELECT COUNT(*) FROM programs
            WHERE network_id = :nid
              AND start_date <= :end AND end_date >= :start
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).scalar() or 0

        # Programs with courses in >= 2 distinct languages
        multilingual = session.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT p.program_id
                FROM programs p
                JOIN courses c ON p.program_id = c.program_id
                WHERE p.network_id = :nid
                  AND p.start_date <= :end AND p.end_date >= :start
                GROUP BY p.program_id
                HAVING COUNT(DISTINCT c.language) >= 2
            ) sub
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).scalar() or 0

        return (multilingual / total * 100) if total > 0 else 0.0

    # ── K08: New Member Growth Rate ───────────────────────────────────────────

    def k08_member_growth_rate(
        self, session, network_id, period_start, period_end
    ) -> float:
        at_start = session.execute(text("""
            SELECT COUNT(*) FROM network_memberships
            WHERE network_id = :nid AND since_date < :start
        """), {"nid": network_id, "start": period_start}).scalar() or 0

        joined_in_period = session.execute(text("""
            SELECT COUNT(*) FROM network_memberships
            WHERE network_id = :nid
              AND since_date BETWEEN :start AND :end
        """), {"nid": network_id, "start": period_start,
               "end": period_end}).scalar() or 0

        return (joined_in_period / at_start * 100) if at_start > 0 else 0.0

    # ── K09: HITL Review Turnaround Time ─────────────────────────────────────

    def k09_hitl_turnaround(
        self, session, network_id, period_start, period_end
    ) -> float:
        rows = session.execute(text("""
            SELECT
                EXTRACT(EPOCH FROM (hr.reviewed_at - al.created_at)) / 3600.0
                AS hours
            FROM audit_logs al
            JOIN hitl_reviews hr ON al.log_id = hr.log_id
            WHERE al.consequence_level = 'high'
              AND al.created_at BETWEEN :start AND :end
        """), {"start": period_start, "end": period_end}).fetchall()

        if not rows:
            return 0.0
        avg_hours = sum(r.hours for r in rows) / len(rows)
        return round(avg_hours, 2)

    # ── K10: Ethics Compliance Rate ───────────────────────────────────────────

    def k10_ethics_compliance_rate(
        self, session, network_id, period_start, period_end
    ) -> float:
        total = session.execute(text("""
            SELECT COUNT(*) FROM audit_logs
            WHERE created_at BETWEEN :start AND :end
        """), {"start": period_start, "end": period_end}).scalar() or 0

        passed = session.execute(text("""
            SELECT COUNT(*) FROM audit_logs
            WHERE all_checks_passed = TRUE
              AND created_at BETWEEN :start AND :end
        """), {"start": period_start, "end": period_end}).scalar() or 0

        return (passed / total * 100) if total > 0 else 100.0

    # ── Writer ────────────────────────────────────────────────────────────────

    def _write(
        self, session, kpi_id: str, scope_id: int,
        period_start: date, period_end: date, value: float,
    ) -> None:
        session.execute(text("""
            INSERT INTO kpi_values
                (kpi_id, scope_type, scope_id, period_start, period_end,
                 value, computed_at)
            VALUES
                (:kpi_id, 'network', :scope_id, :period_start, :period_end,
                 :value, :computed_at)
        """), {
            "kpi_id": kpi_id,
            "scope_id": scope_id,
            "period_start": period_start,
            "period_end": period_end,
            "value": value,
            "computed_at": datetime.now(timezone.utc),
        })