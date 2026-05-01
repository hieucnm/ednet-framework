# modules/governance/hitl_controller.py

from datetime import datetime, timezone
from sqlalchemy import text
from modules.analytics.db_connector import get_session


class HITLController:
    """
    Manages the human-in-the-loop review queue.
    Enqueues high-consequence outputs and records reviewer decisions.
    """

    def enqueue(self, log_id: str, output: str) -> None:
        """Mark a log entry as pending review. Output is already in audit_logs."""
        # Status already set to PENDING_REVIEW by AuditLogger.
        # This method exists as an explicit hook for future notification logic
        # (e.g., sending an email or Slack message to the reviewer pool).
        pass

    def submit_review(
        self,
        log_id: str,
        reviewer_id: str,
        decision: str,
        edited_output: str | None = None,
        review_note: str | None = None,
    ) -> None:
        """
        Record a reviewer's decision for a pending log entry.
        decision must be one of: 'approved', 'edited', 'rejected'
        """
        if decision not in {"approved", "edited", "rejected"}:
            raise ValueError(f"Invalid decision: '{decision}'")

        if decision == "edited" and not edited_output:
            raise ValueError("edited_output is required when decision is 'edited'")

        now = datetime.now(timezone.utc)
        review_id = f"rev_{log_id[:8]}_{now.timestamp():.0f}"

        with get_session() as session:
            session.execute(
                text("""
                    INSERT INTO hitl_reviews (
                        review_id, log_id, reviewer_id, decision,
                        edited_output, review_note, reviewed_at
                    ) VALUES (
                        :review_id, :log_id, :reviewer_id, :decision,
                        :edited_output, :review_note, :reviewed_at
                    )
                """),
                {
                    "review_id": review_id,
                    "log_id": log_id,
                    "reviewer_id": reviewer_id,
                    "decision": decision,
                    "edited_output": edited_output,
                    "review_note": review_note,
                    "reviewed_at": now,
                },
            )
            new_status = "APPROVED" if decision in {"approved", "edited"} else "REJECTED"
            session.execute(
                text("UPDATE audit_logs SET status = :status WHERE log_id = :log_id"),
                {"status": new_status, "log_id": log_id},
            )
            session.commit()

    def get_final_output(self, log_id: str) -> str | None:
        """
        Return the final output for a reviewed log entry.
        If the reviewer edited the output, return the edited version.
        """
        with get_session() as session:
            row = session.execute(
                text("""
                    SELECT al.output_text, hr.edited_output, hr.decision
                    FROM audit_logs al
                    LEFT JOIN hitl_reviews hr ON al.log_id = hr.log_id
                    WHERE al.log_id = :log_id
                """),
                {"log_id": log_id},
            ).fetchone()

        if row is None:
            return None
        if row.decision == "edited" and row.edited_output:
            return row.edited_output
        if row.decision == "approved":
            return row.output_text
        return None