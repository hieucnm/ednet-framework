# orchestrator/coordinator.py

import hashlib
from modules.communication.prompt_engine import PromptEngine
from modules.governance.audit_logger import AuditLogger
from modules.governance.ethics_auditor import EthicsAuditor
from modules.governance.hitl_controller import HITLController
from orchestrator.llm_client import LLMClient

class Orchestrator:

    def __init__(self):
        self.llm = LLMClient()
        self.prompt_engine = PromptEngine()
        self.audit_logger = AuditLogger()
        self.ethics_auditor = EthicsAuditor(llm_client=self.llm)
        self.hitl = HITLController()

    def run_task(
        self,
        template_id: str,
        variables: dict,
        session_id: str,
    ) -> dict:
        # 1. Load and render template
        template = self.prompt_engine.load(template_id)
        system_prompt = template.render_system(variables)
        user_prompt = template.render_user(variables)

        # 2. Call LLM
        response = self.llm.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 3. Run ethics checklist
        audit_result = self.ethics_auditor.evaluate(
            output_text=response.text,
            template_id=template_id,
            language=variables.get("language", "en"),
        )

        # 4. Write audit log
        log_id = self.audit_logger.write(
            session_id=session_id,
            template=template,
            response=response,
            input_hash=hashlib.sha256(
                user_prompt.encode()
            ).hexdigest(),
            audit_result=audit_result,
        )

        # 5. Route based on ethics result and consequence level
        if not audit_result.passed:
            return {
                "status": "BLOCKED",
                "reason": audit_result.failed_checks,
                "output": None,
            }

        if template.consequence_level == "high":
            self.hitl.enqueue(log_id=log_id, output=response.text)
            return {
                "status": "PENDING_REVIEW",
                "log_id": log_id,
                "output": None,
                "message": (
                    "This output requires human review before delivery. "
                    "A reviewer has been notified."
                ),
            }

        return {
            "status": "DELIVERED",
            "output": response.text,
            "log_id": log_id,
        }