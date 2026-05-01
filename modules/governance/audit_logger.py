# modules/governance/audit_logger.py

import uuid
from datetime import datetime, timezone
from sqlalchemy import text
from modules.analytics.db_connector import get_session
from orchestrator.llm_client import LLMResponse
from modules.communication.prompt_engine import PromptTemplate


class AuditLogger:
    """
    Writes LLM interaction records to the audit_logs table.
    Every call to the LLM must produce an audit log entry,
    regardless of whether the output is delivered or blocked.
    """

    def write(
        self,
        session_id: str,
        template: PromptTemplate,
        response: LLMResponse,
        input_hash: str,
        audit_result: "AuditResult",  # noqa: F821 — forward reference
        language: str = "en",
    ) -> str:
        """
        Write a log entry and return the generated log_id.
        """
        log_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with get_session() as session:
            session.execute(
                text("""
                    INSERT INTO audit_logs (
                        log_id, session_id, task_type, template_name,
                        model_provider, model_name, temperature,
                        input_hash, output_text, language,
                        consequence_level, all_checks_passed,
                        failed_checks, status, created_at
                    ) VALUES (
                        :log_id, :session_id, :task_type, :template_name,
                        :model_provider, :model_name, :temperature,
                        :input_hash, :output_text, :language,
                        :consequence_level, :all_checks_passed,
                        :failed_checks, :status, :created_at
                    )
                """),
                {
                    "log_id": log_id,
                    "session_id": session_id,
                    "task_type": template.task_type,
                    "template_name": template.template_id,
                    "model_provider": response.provider,
                    "model_name": response.model,
                    "temperature": 0.3,
                    "input_hash": input_hash,
                    "output_text": response.text,
                    "language": language,
                    "consequence_level": template.consequence_level,
                    "all_checks_passed": audit_result.passed,
                    "failed_checks": ",".join(audit_result.failed_checks),
                    "status": self._initial_status(template, audit_result),
                    "created_at": now,
                },
            )
            session.commit()

        return log_id

    def update_status(self, log_id: str, status: str) -> None:
        with get_session() as session:
            session.execute(
                text("UPDATE audit_logs SET status = :status WHERE log_id = :log_id"),
                {"status": status, "log_id": log_id},
            )
            session.commit()

    def get_pending_reviews(self) -> list[dict]:
        """Return all log entries awaiting human review."""
        with get_session() as session:
            rows = session.execute(
                text("""
                    SELECT log_id, task_type, template_name, language,
                           output_text, created_at
                    FROM audit_logs
                    WHERE status = 'PENDING_REVIEW'
                    ORDER BY created_at ASC
                """)
            ).fetchall()
        return [dict(row._mapping) for row in rows]

    @staticmethod
    def _initial_status(template: PromptTemplate, audit_result) -> str:
        if not audit_result.passed:
            return "BLOCKED"
        if template.consequence_level == "high":
            return "PENDING_REVIEW"
        return "DELIVERED"