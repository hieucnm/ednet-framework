# app/main.py

import uuid
import gradio as gr
from orchestrator.coordinator import Orchestrator
from modules.communication.prompt_engine import PromptEngine
from modules.governance.audit_logger import AuditLogger
from modules.governance.hitl_controller import HITLController

orchestrator = Orchestrator()
prompt_engine = PromptEngine()
audit_logger = AuditLogger()
hitl = HITLController()

# ── Helpers ──────────────────────────────────────────────────────────────────

TASK_CONFIG = {
    "Meeting Minutes": {
        "template_id": "meeting_minutes_v1",
        "extra_fields": ["network_name", "meeting_date"],
    },
    "Document Summarizer": {
        "template_id": "document_summarizer_v1",
        "extra_fields": [],
    },
    "Curriculum Designer": {
        "template_id": "curriculum_designer_v1",
        "extra_fields": ["program_name", "institutions", "goals", "audience",
                         "duration", "constraints"],
    },
    "Lecture Generator": {
        "template_id": "lecture_generator_v1",
        "extra_fields": ["course_name", "topic", "objectives", "level", "duration"],
    },
    "Collaboration Framework": {
        "template_id": "collaboration_framework_v1",
        "extra_fields": ["institutions", "purpose", "period",
                         "activities", "constraints"],
    },
}

LANGUAGE_OPTIONS = ["en", "vi", "fr"]


def format_status_badge(status: str) -> str:
    badges = {
        "DELIVERED":       "✅ Delivered",
        "PENDING_REVIEW":  "⏳ Pending Human Review",
        "BLOCKED":         "🚫 Blocked by Ethics Check",
        "APPROVED":        "✅ Approved by Reviewer",
        "REJECTED":        "❌ Rejected by Reviewer",
    }
    return badges.get(status, status)


# ── Tab 1: Run Task ───────────────────────────────────────────────────────────

def run_task(
    task_name, language, input_text,
    network_name, meeting_date,
    program_name, institutions, goals, audience,
    duration, constraints, course_name, topic,
    objectives, level, purpose, period, activities,
):
    if not input_text.strip():
        return (
            gr.update(value="⚠️ Please provide input text.", visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    config = TASK_CONFIG[task_name]
    template_id = config["template_id"]

    variables = {
        "language": language,
        "input_text": input_text,
        "network_name": network_name or "N/A",
        "meeting_date": meeting_date or "N/A",
        "program_name": program_name or "N/A",
        "institutions": institutions or "N/A",
        "goals": goals or "N/A",
        "audience": audience or "N/A",
        "duration": duration or "N/A",
        "constraints": constraints or "None",
        "course_name": course_name or "N/A",
        "topic": topic or "N/A",
        "objectives": objectives or "N/A",
        "level": level or "N/A",
        "purpose": purpose or "N/A",
        "period": period or "N/A",
        "activities": activities or "N/A",
    }

    session_id = str(uuid.uuid4())
    result = orchestrator.run_task(
        template_id=template_id,
        variables=variables,
        session_id=session_id,
    )

    status_text = format_status_badge(result["status"])

    if result["status"] == "BLOCKED":
        reasons = "\n".join(f"- {r}" for r in result.get("reason", []))
        return (
            gr.update(
                value=f"**{status_text}**\n\nThis output was blocked for the "
                      f"following reasons:\n{reasons}",
                visible=True,
            ),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    if result["status"] == "PENDING_REVIEW":
        return (
            gr.update(
                value=f"**{status_text}**\n\n"
                      f"Log ID: `{result['log_id']}`\n\n"
                      f"{result['message']}",
                visible=True,
            ),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    # DELIVERED
    return (
        gr.update(
            value=f"**{status_text}** | Log ID: `{result['log_id']}`",
            visible=True,
        ),
        gr.update(value=result["output"], visible=True),
        gr.update(visible=True),
    )


# ── Tab 2: HITL Review Queue ──────────────────────────────────────────────────

def load_review_queue():
    pending = audit_logger.get_pending_reviews()
    if not pending:
        return gr.update(choices=[], value=None), "No outputs are currently pending review."

    choices = [
        f"{p['log_id'][:8]}... | {p['task_type']} | {p['language']} | "
        f"{str(p['created_at'])[:16]}"
        for p in pending
    ]
    log_ids = [p["log_id"] for p in pending]

    # Store mapping in a simple module-level dict
    global _pending_map
    _pending_map = dict(zip(choices, log_ids))

    return gr.update(choices=choices, value=choices[0]), ""


_pending_map = {}


def load_selected_output(choice):
    if not choice or choice not in _pending_map:
        return "", ""
    log_id = _pending_map[choice]
    pending = audit_logger.get_pending_reviews()
    entry = next((p for p in pending if p["log_id"] == log_id), None)
    if entry is None:
        return "", log_id
    return entry["output_text"], log_id


def submit_review(log_id, reviewer_id, decision, edited_text, note):
    if not log_id:
        return "⚠️ No output selected for review."
    if not reviewer_id.strip():
        return "⚠️ Reviewer ID is required."

    if decision == "Approve":
        hitl.submit_review(log_id, reviewer_id, "approved", review_note=note)
        return f"✅ Output `{log_id[:8]}...` approved."
    elif decision == "Approve with Edits":
        if not edited_text.strip():
            return "⚠️ Please provide edited text before submitting."
        hitl.submit_review(log_id, reviewer_id, "edited", edited_text, note)
        return f"✅ Edited output for `{log_id[:8]}...` approved."
    elif decision == "Reject":
        hitl.submit_review(log_id, reviewer_id, "rejected", review_note=note)
        return f"❌ Output `{log_id[:8]}...` rejected."


# ── Build UI ──────────────────────────────────────────────────────────────────

def build_ui():
    with gr.Blocks(
        title="EdNet AI Framework",
        theme=gr.themes.Soft(),
    ) as demo:

        gr.Markdown(
            "# 🎓 EdNet AI-Enabled Framework\n"
            "**Multilingual Communication Toolkit** for Education and Training Networks"
        )

        with gr.Tabs():

            # ── Tab 1: Communication Tasks ──
            with gr.TabItem("📝 Communication Tasks"):

                gr.Markdown(
                    "Upload or paste a document, select a task and output language, "
                    "then click **Run Task**. High-consequence outputs will be sent "
                    "to the human review queue before delivery."
                )

                with gr.Row():
                    with gr.Column(scale=1):

                        task_selector = gr.Dropdown(
                            choices=list(TASK_CONFIG.keys()),
                            value="Meeting Minutes",
                            label="Task",
                        )
                        language_selector = gr.Dropdown(
                            choices=LANGUAGE_OPTIONS,
                            value="en",
                            label="Output Language",
                        )

                        gr.Markdown("### Input")
                        input_text = gr.Textbox(
                            lines=10,
                            placeholder="Paste transcript, document, or brief here...",
                            label="Input Text",
                        )

                        # Context fields — shown/hidden based on task
                        gr.Markdown("### Task-specific Fields *(fill only what applies)*")
                        network_name = gr.Textbox(label="Network Name", visible=True)
                        meeting_date = gr.Textbox(label="Meeting Date", visible=True)
                        program_name = gr.Textbox(label="Program Name", visible=False)
                        institutions = gr.Textbox(label="Institutions", visible=False)
                        goals = gr.Textbox(label="Program / Collaboration Goals",
                                           lines=3, visible=False)
                        audience = gr.Textbox(label="Target Audience", visible=False)
                        duration = gr.Textbox(label="Duration", visible=False)
                        constraints = gr.Textbox(label="Constraints / Conditions",
                                                 visible=False)
                        course_name = gr.Textbox(label="Course Name", visible=False)
                        topic = gr.Textbox(label="Lecture Topic", visible=False)
                        objectives = gr.Textbox(label="Learning Objectives",
                                                lines=3, visible=False)
                        level = gr.Dropdown(
                            choices=["Undergraduate", "Graduate", "Professional"],
                            label="Audience Level",
                            visible=False,
                        )
                        purpose = gr.Textbox(label="Purpose of Collaboration",
                                             visible=False)
                        period = gr.Textbox(label="Effective Period", visible=False)
                        activities = gr.Textbox(label="Key Planned Activities",
                                                lines=3, visible=False)

                        run_btn = gr.Button("▶ Run Task", variant="primary")

                    with gr.Column(scale=1):
                        status_box = gr.Markdown(visible=False)
                        output_box = gr.Textbox(
                            lines=20,
                            label="AI-Generated Output (Draft)",
                            visible=False,
                            show_copy_button=True,
                        )
                        copy_note = gr.Markdown(
                            "_This output is a draft. "
                            "High-consequence outputs require human review "
                            "before official use._",
                            visible=False,
                        )

                # Dynamic field visibility based on task selection
                def update_fields(task):
                    show = TASK_CONFIG[task]["extra_fields"]
                    return (
                        gr.update(visible="network_name" in show or task == "Meeting Minutes"),
                        gr.update(visible="meeting_date" in show or task == "Meeting Minutes"),
                        gr.update(visible="program_name" in show),
                        gr.update(visible="institutions" in show),
                        gr.update(visible="goals" in show),
                        gr.update(visible="audience" in show),
                        gr.update(visible="duration" in show),
                        gr.update(visible="constraints" in show),
                        gr.update(visible="course_name" in show),
                        gr.update(visible="topic" in show),
                        gr.update(visible="objectives" in show),
                        gr.update(visible="level" in show),
                        gr.update(visible="purpose" in show),
                        gr.update(visible="period" in show),
                        gr.update(visible="activities" in show),
                    )

                task_selector.change(
                    fn=update_fields,
                    inputs=[task_selector],
                    outputs=[
                        network_name, meeting_date, program_name, institutions,
                        goals, audience, duration, constraints, course_name,
                        topic, objectives, level, purpose, period, activities,
                    ],
                )

                run_btn.click(
                    fn=run_task,
                    inputs=[
                        task_selector, language_selector, input_text,
                        network_name, meeting_date, program_name, institutions,
                        goals, audience, duration, constraints, course_name,
                        topic, objectives, level, purpose, period, activities,
                    ],
                    outputs=[status_box, output_box, copy_note],
                )

            # ── Tab 2: HITL Review Queue ──
            with gr.TabItem("👤 Review Queue"):

                gr.Markdown(
                    "### Human Review Queue\n"
                    "High-consequence AI outputs awaiting review. "
                    "Select an entry, review the draft, and submit your decision."
                )

                refresh_btn = gr.Button("🔄 Refresh Queue")
                queue_status = gr.Markdown()
                queue_selector = gr.Dropdown(
                    choices=[],
                    label="Pending Outputs",
                    interactive=True,
                )

                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("**AI-Generated Draft (read-only)**")
                        draft_display = gr.Textbox(
                            lines=15,
                            label="Draft Output",
                            interactive=False,
                        )
                        hidden_log_id = gr.Textbox(visible=False)

                    with gr.Column(scale=1):
                        gr.Markdown("**Your Review**")
                        reviewer_id = gr.Textbox(
                            label="Your Reviewer ID",
                            placeholder="e.g. staff_001",
                        )
                        decision = gr.Radio(
                            choices=["Approve", "Approve with Edits", "Reject"],
                            label="Decision",
                            value="Approve",
                        )
                        edited_output = gr.Textbox(
                            lines=10,
                            label="Edited Output *(required if 'Approve with Edits')*",
                            placeholder="Paste your corrected version here...",
                            visible=False,
                        )
                        review_note = gr.Textbox(
                            label="Review Note *(optional)*",
                            placeholder="Reason for edit or rejection...",
                        )
                        submit_btn = gr.Button("Submit Review", variant="primary")
                        review_result = gr.Markdown()

                # Show edited output field only when needed
                decision.change(
                    fn=lambda d: gr.update(visible=(d == "Approve with Edits")),
                    inputs=[decision],
                    outputs=[edited_output],
                )

                refresh_btn.click(
                    fn=load_review_queue,
                    outputs=[queue_selector, queue_status],
                )

                queue_selector.change(
                    fn=load_selected_output,
                    inputs=[queue_selector],
                    outputs=[draft_display, hidden_log_id],
                )

                submit_btn.click(
                    fn=submit_review,
                    inputs=[
                        hidden_log_id, reviewer_id, decision,
                        edited_output, review_note,
                    ],
                    outputs=[review_result],
                )

            # ── Tab 3: Template Reference ──
            with gr.TabItem("📚 Template Reference"):

                gr.Markdown("### Available Prompt Templates")

                def load_template_catalog():
                    templates = prompt_engine.list_available()
                    rows = "\n".join(
                        f"| `{t['template_id']}` | {t['task_type']} | "
                        f"{t['consequence_level']} | "
                        f"{', '.join(t['supported_languages'])} |"
                        for t in templates
                    )
                    return (
                        "| Template ID | Task Type | Consequence | Languages |\n"
                        "|---|---|---|---|\n"
                        + rows
                    )

                gr.Markdown(load_template_catalog())

                gr.Markdown(
                    "### Consequence Levels\n"
                    "- **High** → Output held in review queue until a human "
                    "reviewer approves it.\n"
                    "- **Medium** → Output delivered immediately; review recommended.\n"
                    "- **Low** → Output delivered immediately."
                )

    return demo


if __name__ == "__main__":
    app = build_ui()
    app.launch(server_name="0.0.0.0", server_port=7860)