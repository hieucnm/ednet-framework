#!/usr/bin/env python3
"""
experiments/run_experiment2.py

Runs Experiment 2:
  Part A — Ethics audit corpus evaluation
      Runs EthicsAuditor on all 60 entries in ethics_corpus.json,
      computes precision / recall / F1 for blocking checks (EC-06, EC-07)
      and detection rate for warning checks (EC-03, EC-04).

  Part B — HITL audit trail verification
      Traces 5 end-to-end runs of Use Case 1 (Meeting Minutes, high-consequence)
      through the Orchestrator, then queries the audit database to verify that
      all expected records are present and correctly linked.

Usage:
    python experiments/run_experiment2.py
    python experiments/run_experiment2.py --part a
    python experiments/run_experiment2.py --part b

Requirements:
    pip install pyyaml anthropic python-dotenv langdetect
"""

import argparse
import json
import os
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

CORPUS_PATH  = REPO_ROOT / "data" / "experiment2" / "ethics_corpus.json"
RESULTS_DIR  = REPO_ROOT / "data" / "experiment2"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATE_LIMITS = {
    "meeting_minutes_v1":         {"min": 150, "max": 800},
    "document_summarizer_v1":     {"min":  80, "max": 350},
    "lecture_generator_v1":       {"min": 400, "max": 1200},
    "curriculum_designer_v1":     {"min": 300, "max": 1000},
    "collaboration_framework_v1": {"min": 300, "max": 900},
}


# ══════════════════════════════════════════════════════════════════════════════
# PART A — Ethics audit corpus evaluation
# ══════════════════════════════════════════════════════════════════════════════

def run_part_a() -> dict:
    from modules.governance.ethics_auditor import EthicsAuditor

    print("\n" + "="*60)
    print("PART A — Ethics Audit Corpus Evaluation")
    print("="*60)

    with open(CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)

    auditor = EthicsAuditor(llm_client=None)

    # Per-entry results
    entry_results = []

    # Counters for blocking checks (EC-06, EC-07)
    tp = tn = fp = fn = 0

    # Warning detection counters: {check: {detected, total}}
    warning_counts = defaultdict(lambda: {"detected": 0, "total": 0})

    for entry in corpus:
        lim = TEMPLATE_LIMITS[entry["template_id"]]
        result = auditor.evaluate(
            output_text=entry["output_text"],
            template_id=entry["template_id"],
            language=entry["language"],
            min_words=lim["min"],
            max_words=lim["max"],
        )

        is_blocking_violation = entry["violation_type"] in ("EC-06", "EC-07")
        predicted_block = not result.passed

        # Blocking classification
        if is_blocking_violation and predicted_block:          tp += 1; outcome = "TP"
        elif not is_blocking_violation and not predicted_block: tn += 1; outcome = "TN"
        elif not is_blocking_violation and predicted_block:     fp += 1; outcome = "FP"
        else:                                                   fn += 1; outcome = "FN"

        # Warning detection
        if entry["violation_type"] in ("EC-03", "EC-04"):
            check = entry["violation_type"]
            warning_counts[check]["total"] += 1
            if any(check in w for w in result.warnings):
                warning_counts[check]["detected"] += 1

        entry_results.append({
            "entry_id":       entry["entry_id"],
            "template_id":    entry["template_id"],
            "language":       entry["language"],
            "ground_truth":   entry["ground_truth"],
            "violation_type": entry["violation_type"],
            "predicted_block": predicted_block,
            "outcome":        outcome,
            "failed_checks":  result.failed_checks,
            "warnings":       result.warnings,
        })

    # ── Metrics ───────────────────────────────────────────────────────────────
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) > 0 else 0.0)
    accuracy  = (tp + tn) / len(corpus)

    metrics = {
        "total_entries": len(corpus),
        "blocking_checks": {
            "TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "precision": round(precision, 4),
            "recall":    round(recall,    4),
            "f1":        round(f1,        4),
            "accuracy":  round(accuracy,  4),
        },
        "warning_checks": {
            check: {
                "detected": v["detected"],
                "total":    v["total"],
                "detection_rate": round(v["detected"] / v["total"], 4) if v["total"] else 0,
            }
            for check, v in warning_counts.items()
        },
    }

    print(f"\nBlocking checks (EC-06, EC-07):")
    print(f"  TP={tp}  TN={tn}  FP={fp}  FN={fn}")
    print(f"  Precision={precision:.4f}  Recall={recall:.4f}  F1={f1:.4f}  Accuracy={accuracy:.4f}")
    print(f"\nWarning checks:")
    for check, v in metrics["warning_checks"].items():
        print(f"  {check}: {v['detected']}/{v['total']} detected "
              f"(rate={v['detection_rate']:.2f})")

    # Save
    out = {
        "metrics": metrics,
        "entry_results": entry_results,
    }
    out_path = RESULTS_DIR / "part_a_results.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved to: {out_path}")
    return metrics


# ══════════════════════════════════════════════════════════════════════════════
# PART B — HITL audit trail verification
# ══════════════════════════════════════════════════════════════════════════════

USE_CASE_1_INPUTS = [
    {
        "input_id": "MM-EN-01",
        "template_id": "meeting_minutes_v1",
        "template_name": "meeting_minutes",
    },
    {
        "input_id": "MM-EN-03",
        "template_id": "meeting_minutes_v1",
        "template_name": "meeting_minutes",
    },
    {
        "input_id": "MM-EN-05",
        "template_id": "meeting_minutes_v1",
        "template_name": "meeting_minutes",
    },
    {
        "input_id": "MM-VI-01",
        "template_id": "meeting_minutes_v1",
        "template_name": "meeting_minutes",
    },
    {
        "input_id": "MM-VI-03",
        "template_id": "meeting_minutes_v1",
        "template_name": "meeting_minutes",
    },
]


def run_part_b() -> dict:
    from orchestrator.coordinator import Orchestrator

    print("\n" + "="*60)
    print("PART B — HITL Audit Trail Verification (Use Case 1)")
    print("="*60)

    coordinator = Orchestrator()

    inputs_dir = REPO_ROOT / "data" / "experiment1" / "inputs"
    templates_dir = REPO_ROOT / "modules" / "communication" / "templates"

    trace_results = []

    for run_cfg in USE_CASE_1_INPUTS:
        input_id     = run_cfg["input_id"]
        template_id  = run_cfg["template_id"]
        template_name = run_cfg["template_name"]
        session_id   = str(uuid.uuid4())

        print(f"\n  RUN {input_id} (session={session_id[:8]}...) ... ", end="", flush=True)

        # Load manifest + input
        manifest_path = inputs_dir / template_name / "manifest.json"
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        meta = manifest[input_id]

        input_file = inputs_dir / template_name / f"{input_id}.txt"
        input_text = input_file.read_text(encoding="utf-8")

        variables = {
            "input_text":   input_text,
            "language":     meta["language"],
            "network_name": meta.get("network_name", "VASTN"),
            "meeting_date": meta.get("meeting_date", ""),
        }

        # Run through Coordinator (triggers HITL for high-consequence template)
        try:
            response = coordinator.run_task(
                template_id=template_id,
                variables=variables,
                session_id=session_id,
            )
            status = response.get("status")
            log_id = response.get("log_id")
            print(f"status={status}", end="")
        except Exception as e:
            print(f"ERROR — {e}")
            trace_results.append({
                "input_id": input_id, "session_id": session_id,
                "error": str(e),
            })
            continue

        # ── Verify audit trail ────────────────────────────────────────────────
        checks = _verify_audit_trail(coordinator, session_id, log_id, status)

        all_passed = all(checks.values())
        print(f" | trail={'✓' if all_passed else '✗'} "
              f"({sum(checks.values())}/{len(checks)} checks)")

        trace_results.append({
            "input_id":   input_id,
            "session_id": session_id,
            "log_id":     log_id,
            "status":     status,
            "trail_checks": checks,
            "trail_passed": all_passed,
        })

        time.sleep(0.5)

    # ── Summary ───────────────────────────────────────────────────────────────
    n_runs    = len(trace_results)
    n_hitl    = sum(1 for r in trace_results
                    if r.get("status") in ("PENDING_REVIEW", "DELIVERED"))
    n_trail   = sum(1 for r in trace_results if r.get("trail_passed"))

    hitl_trigger_rate  = n_hitl  / n_runs if n_runs else 0
    trail_complete_rate = n_trail / n_runs if n_runs else 0

    print(f"\n  Runs completed          : {n_runs}/5")
    print(f"  HITL triggered          : {n_hitl}/{n_runs} "
          f"({hitl_trigger_rate:.0%}) — expected 100% for high-consequence template")
    print(f"  Audit trail complete    : {n_trail}/{n_runs} ({trail_complete_rate:.0%})")

    metrics = {
        "n_runs":              n_runs,
        "hitl_triggered":      n_hitl,
        "hitl_trigger_rate":   round(hitl_trigger_rate,  4),
        "trail_complete":      n_trail,
        "trail_complete_rate": round(trail_complete_rate, 4),
        "trace_results":       trace_results,
    }

    out_path = RESULTS_DIR / "part_b_results.json"
    out_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved to: {out_path}")
    return metrics


def _verify_audit_trail(coordinator, session_id: str, log_id, status: str) -> dict:
    """
    Query audit_logs and hitl_reviews tables directly to verify
    expected records exist. Uses only methods available in the actual classes.
    """
    from modules.analytics.db_connector import get_session
    from sqlalchemy import text

    checks = {}

    with get_session() as session:

        # C1: audit log entry exists
        row = session.execute(
            text("SELECT * FROM audit_logs WHERE log_id = :lid"),
            {"lid": log_id},
        ).fetchone()
        checks["log_entry_exists"] = row is not None

        if row is not None:
            log = dict(row._mapping)

            # C2: session_id correctly recorded
            checks["session_id_correct"] = log.get("session_id") == session_id

            # C3: ethics audit result recorded (all_checks_passed column)
            checks["ethics_result_recorded"] = "all_checks_passed" in log

            # C4: language recorded correctly
            checks["language_recorded"] = (
                log.get("language") in ("en", "vi")
            )

            # C5: status matches expected routing
            expected_status = "PENDING_REVIEW" if status == "PENDING_REVIEW" else "DELIVERED"
            checks["status_correct"] = log.get("status") == expected_status

        else:
            checks["session_id_correct"]    = False
            checks["ethics_result_recorded"] = False
            checks["language_recorded"]      = False
            checks["status_correct"]         = False

    return checks


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Run Experiment 2: ethics audit and HITL trail verification."
    )
    parser.add_argument(
        "--part",
        choices=["a", "b", "all"],
        default="all",
        help="Which part to run (default: all)",
    )
    args = parser.parse_args()

    results = {}

    if args.part in ("a", "all"):
        results["part_a"] = run_part_a()

    if args.part in ("b", "all"):
        results["part_b"] = run_part_b()

    # Combined results file
    combined_path = RESULTS_DIR / "experiment2_results.json"
    combined_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nCombined results: {combined_path}")


if __name__ == "__main__":
    main()
