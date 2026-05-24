#!/usr/bin/env python3
"""
experiments/run_experiment1.py

Runs Experiment 1: generates outputs for all 40 input documents across two models
(claude-sonnet-4-6 and gpt-4o), then computes:
  - ROUGE-1, ROUGE-2, ROUGE-L  (meeting_minutes, document_summarizer only)
  - Structure compliance rate   (all templates)
  - Mean latency per model/template/language

Usage:
    python experiments/run_experiment1.py
    python experiments/run_experiment1.py --models claude --dry-run
    python experiments/run_experiment1.py --skip-existing

Requirements:
    pip install rouge-score pyyaml anthropic openai python-dotenv
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

INPUTS_DIR   = REPO_ROOT / "data" / "experiment1" / "inputs"
REFS_DIR     = REPO_ROOT / "data" / "experiment1" / "references"
OUTPUTS_DIR  = REPO_ROOT / "data" / "experiment1" / "outputs"
RESULTS_FILE = REPO_ROOT / "data" / "experiment1" / "results.json"
TEMPLATES_DIR = REPO_ROOT / "modules" / "communication" / "templates"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Model configs ──────────────────────────────────────────────────────────────

MODELS = {
    "claude": {
        "provider": "anthropic",
        "model_id": "claude-sonnet-4-6",
    },
    "gpt4o": {
        "provider": "openai",
        "model_id": "gpt-4o",
    },
}

# Templates that get ROUGE scoring (need reference outputs)
ROUGE_TEMPLATES = {"meeting_minutes_v1", "document_summarizer_v1"}

# Required structure markers per template (regex patterns)
STRUCTURE_MARKERS = {
    "meeting_minutes_v1": [
        r"##\s+Meeting Minutes|##\s+Biên bản",
        r"\*\*Network\*\*|\*\*Mạng lưới\*\*|\*\*Network:\*\*|\*\*Mạng",
        r"###\s+(Action Items|Agenda|Nhiệm vụ|Nội dung|Hạng mục)",
        r"\|.*\|.*\|",
    ],
    "document_summarizer_v1": [
        r"##\s+(Document Summary|Summary|Tóm tắt)",
        r"\*\*(Source|Document type|Nguồn|Loại tài liệu)",
    ],
    "lecture_generator_v1": [
        r"##\s+(Lecture|Kế hoạch|Bài giảng)",
        r"###\s*(Learning Objectives|Mục tiêu|Session Outline|Phác thảo)",
        r"(###\s+Part|###\s+Phần|\*\*(Part|Phần))\s+\d",
    ],
    "curriculum_designer_v1": [
        r"##\s+(Curriculum|Programme|Chương trình)",
        r"###\s+(Programme|Assessment|Đánh giá|Structure|Cấu trúc|Rationale)",
        r"\|.*\|.*\|",
    ],
    "collaboration_framework_v1": [
        r"##\s+Collaboration Framework",
        r"\*\*Parties:\*\*|\*\*Purpose:\*\*",
        r"###\s+(Scope|Responsibilities|Governance)",
        r"\[LEGAL REVIEW REQUIRED\]",
    ],
}


# ── LLM callers ────────────────────────────────────────────────────────────────

def call_claude(system_prompt: str, user_prompt: str, model_id: str) -> tuple[str, float]:
    import anthropic
    import os
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    t0 = time.perf_counter()
    msg = client.messages.create(
        model=model_id,
        max_tokens=2048,
        temperature=0.3,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    latency = time.perf_counter() - t0
    return msg.content[0].text, latency


def call_openai(system_prompt: str, user_prompt: str, model_id: str) -> tuple[str, float]:
    import os
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model_id,
        temperature=0.3,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
    )
    latency = time.perf_counter() - t0
    return resp.choices[0].message.content, latency


# ── Template helpers ───────────────────────────────────────────────────────────

def load_template(template_id: str) -> dict:
    path = TEMPLATES_DIR / f"{template_id}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def render(template_str: str, variables: dict) -> str:
    from jinja2 import Environment, StrictUndefined
    return Environment(undefined=StrictUndefined).from_string(template_str).render(**variables)


def load_input_variables(template_name: str, input_id: str, meta: dict) -> dict:
    """
    Build the variables dict for prompt rendering.
    Plain-text templates (meeting_minutes, document_summarizer):
        read .txt file → input_text
    YAML templates (lecture_generator, curriculum_designer, collaboration_framework):
        parse .yaml file → field-by-field variables
    """
    input_dir = INPUTS_DIR / template_name

    if template_name in ("meeting_minutes", "document_summarizer"):
        txt_path = input_dir / f"{input_id}.txt"
        input_text = txt_path.read_text(encoding="utf-8")
        variables = {"input_text": input_text, "language": meta["language"]}
        # meeting_minutes needs extra fields
        if "network_name" in meta:
            variables["network_name"] = meta["network_name"]
        if "meeting_date" in meta:
            variables["meeting_date"] = meta["meeting_date"]

    else:  # lecture_generator, curriculum_designer
        yaml_path = input_dir / f"{input_id}.yaml"
        variables = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        # Ensure language key present
        if "language" not in variables:
            variables["language"] = meta.get("language", "en")

    return variables


# ── Scoring ────────────────────────────────────────────────────────────────────

def score_rouge(hypothesis: str, reference: str) -> dict:
    from rouge_score import rouge_scorer
    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=False)
    scores = scorer.score(reference, hypothesis)
    return {
        "rouge1_f": round(scores["rouge1"].fmeasure, 4),
        "rouge2_f": round(scores["rouge2"].fmeasure, 4),
        "rougeL_f": round(scores["rougeL"].fmeasure, 4),
    }


def score_structure(output_text: str, template_id: str) -> dict:
    markers = STRUCTURE_MARKERS.get(template_id, [])
    if not markers:
        return {"compliant": None, "markers_found": 0, "markers_total": 0}
    found = sum(1 for m in markers if re.search(m, output_text, re.IGNORECASE))
    compliant = found == len(markers)
    return {
        "compliant": compliant,
        "markers_found": found,
        "markers_total": len(markers),
    }


# ── Main runner ────────────────────────────────────────────────────────────────

def run_experiment1(
    model_keys: list[str],
    dry_run: bool = False,
    skip_existing: bool = True,
) -> None:

    all_results = []

    # Load existing results if skip_existing
    if skip_existing and RESULTS_FILE.exists():
        with open(RESULTS_FILE, encoding="utf-8") as f:
            all_results = json.load(f)
        existing_keys = {
            (r["input_id"], r["model_key"]) for r in all_results
        }
        print(f"Loaded {len(all_results)} existing results.")
    else:
        existing_keys = set()

    for model_key in model_keys:
        model_cfg = MODELS[model_key]
        print(f"\n{'='*60}")
        print(f"Model: {model_cfg['model_id']}  ({model_key})")
        print(f"{'='*60}")

        for template_name in [
            "meeting_minutes",
            "document_summarizer",
            "lecture_generator",
            "curriculum_designer",
            "collaboration_framework",
        ]:
            template_id = f"{template_name}_v1"
            input_dir = INPUTS_DIR / template_name
            manifest_path = input_dir / "manifest.json"

            if not manifest_path.exists():
                print(f"  SKIP {template_id}: manifest not found")
                continue

            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            tmpl = load_template(template_id)

            for input_id, meta in sorted(manifest.items()):
                key = (input_id, model_key)
                if skip_existing and key in existing_keys:
                    print(f"  SKIP  {input_id} / {model_key} (already done)")
                    continue

                lang = meta["language"]
                print(f"  RUN   {input_id} [{lang.upper()}] {model_key} ... ", end="", flush=True)

                if dry_run:
                    print("DRY")
                    continue

                # Build variables and render prompts
                try:
                    variables = load_input_variables(template_name, input_id, meta)
                    system_prompt = render(tmpl["system_prompt"], variables)
                    user_prompt   = render(tmpl["user_prompt_template"], variables)
                except Exception as e:
                    print(f"RENDER ERROR — {e}")
                    continue

                # Call LLM
                try:
                    if model_cfg["provider"] == "anthropic":
                        output_text, latency = call_claude(
                            system_prompt, user_prompt, model_cfg["model_id"]
                        )
                    else:
                        output_text, latency = call_openai(
                            system_prompt, user_prompt, model_cfg["model_id"]
                        )
                except Exception as e:
                    print(f"API ERROR — {e}")
                    continue

                # Save raw output
                out_dir = OUTPUTS_DIR / template_name / model_key
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / f"{input_id}.txt").write_text(output_text, encoding="utf-8")

                # Score structure compliance
                structure = score_structure(output_text, template_id)

                # Score ROUGE (if reference exists)
                rouge = None
                if template_id in ROUGE_TEMPLATES:
                    ref_path = REFS_DIR / template_name / f"{input_id}_ref.txt"
                    if ref_path.exists():
                        reference = ref_path.read_text(encoding="utf-8")
                        rouge = score_rouge(output_text, reference)
                    else:
                        print(f"[WARN: no reference at {ref_path}] ", end="")

                result = {
                    "input_id":    input_id,
                    "template_id": template_id,
                    "language":    lang,
                    "model_key":   model_key,
                    "model_id":    model_cfg["model_id"],
                    "latency_s":   round(latency, 3),
                    "word_count":  len(output_text.split()),
                    "structure":   structure,
                    "rouge":       rouge,
                }
                all_results.append(result)

                status = "✓" if structure["compliant"] else "✗"
                rouge_str = (
                    f"R-L={rouge['rougeL_f']:.3f}" if rouge else "ROUGE=n/a"
                )
                print(f"{latency:.1f}s | struct={status} | {rouge_str}")

                # Save incrementally after each call
                with open(RESULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(all_results, f, ensure_ascii=False, indent=2)

                time.sleep(0.5)  # polite rate-limit buffer

    if not dry_run:
        _print_summary(all_results)


def _print_summary(results: list[dict]) -> None:
    from collections import defaultdict
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    # Group by model × template × language
    groups: dict = defaultdict(list)
    for r in results:
        key = (r["model_key"], r["template_id"], r["language"])
        groups[key].append(r)

    header = f"{'Model':<8} {'Template':<30} {'Lang':<5} {'N':>3} {'Struct%':>8} {'R-L':>7} {'Lat(s)':>8}"
    print(header)
    print("-" * len(header))

    for key in sorted(groups):
        model_key, template_id, lang = key
        rows = groups[key]
        n = len(rows)
        struct_pct = (
            100 * sum(1 for r in rows if r["structure"]["compliant"]) / n
        )
        rouge_vals = [r["rouge"]["rougeL_f"] for r in rows if r.get("rouge")]
        rouge_mean = sum(rouge_vals) / len(rouge_vals) if rouge_vals else float("nan")
        lat_mean   = sum(r["latency_s"] for r in rows) / n
        rouge_str  = f"{rouge_mean:.3f}" if rouge_vals else "  n/a"
        print(
            f"{model_key:<8} {template_id:<30} {lang:<5} {n:>3} "
            f"{struct_pct:>7.1f}% {rouge_str:>7} {lat_mean:>8.2f}s"
        )

    print(f"\nFull results saved to: {RESULTS_FILE}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run Experiment 1: LLM output quality evaluation."
    )
    parser.add_argument(
        "--models",
        nargs="+",
        choices=list(MODELS.keys()) + ["all"],
        default=["all"],
        help="Which models to run (default: all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would run without calling any API",
    )
    parser.add_argument(
        "--skip-existing", action="store_true", default=True,
        help="Skip input/model combinations already in results.json",
    )
    parser.add_argument(
        "--no-skip", action="store_true",
        help="Re-run everything even if results already exist",
    )
    args = parser.parse_args()

    model_keys = list(MODELS.keys()) if "all" in args.models else args.models
    skip = not args.no_skip

    if args.dry_run:
        print("DRY RUN — no API calls\n")

    run_experiment1(model_keys=model_keys, dry_run=args.dry_run, skip_existing=skip)


if __name__ == "__main__":
    main()
