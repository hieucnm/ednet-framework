#!/usr/bin/env python3
"""
generate_references.py

Generates reference outputs for ROUGE evaluation using GPT-4o.
Applies to Meeting Minutes (MM) and Document Summarizer (DS) templates only.
Reference outputs are saved to data/experiment1/references/.

Usage:
    python data/experiment1/generate_references.py
    python data/experiment1/generate_references.py --template meeting_minutes
    python data/experiment1/generate_references.py --dry-run

Requirements:
    - OPENAI_API_KEY set in environment or .env file
    - pip install openai pyyaml python-dotenv
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
INPUTS_DIR = REPO_ROOT / "data" / "experiment1" / "inputs"
REFS_DIR = REPO_ROOT / "data" / "experiment1" / "references"
TEMPLATES_DIR = REPO_ROOT / "modules" / "communication" / "templates"

REFS_DIR.mkdir(parents=True, exist_ok=True)

# ── Templates to evaluate ─────────────────────────────────────────────────────

ROUGE_TEMPLATES = ["meeting_minutes", "document_summarizer"]

# ── GPT-4o config ─────────────────────────────────────────────────────────────

REFERENCE_MODEL = "gpt-4o"
TEMPERATURE = 0.3      # same as primary model setting
MAX_TOKENS = 2048


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_prompt_template(template_id: str) -> dict:
    """Load system_prompt and user_prompt_template from YAML."""
    path = TEMPLATES_DIR / f"{template_id}_v1.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_manifest(template_dir: Path) -> dict:
    manifest_path = template_dir / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


def render_jinja(template_str: str, variables: dict) -> str:
    """Simple Jinja2 rendering — mirrors prompt_engine.py logic."""
    from jinja2 import Environment, StrictUndefined
    env = Environment(undefined=StrictUndefined)
    return env.from_string(template_str).render(**variables)


def build_variables(input_id: str, meta: dict, input_text: str) -> dict:
    """Build variables dict for prompt rendering."""
    variables = {
        "input_text": input_text,
        "language": meta["language"],
    }
    # Meeting minutes needs extra metadata
    if "network_name" in meta:
        variables["network_name"] = meta["network_name"]
    if "meeting_date" in meta:
        variables["meeting_date"] = meta["meeting_date"]
    return variables


def call_gpt4o(client: OpenAI, system_prompt: str, user_prompt: str) -> str:
    """Call GPT-4o and return the response text."""
    response = client.chat.completions.create(
        model=REFERENCE_MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
    )
    return response.choices[0].message.content


def output_path(template_name: str, input_id: str) -> Path:
    out_dir = REFS_DIR / template_name
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{input_id}_ref.txt"


# ── Main generation logic ─────────────────────────────────────────────────────

def generate_references(
    templates: list[str],
    dry_run: bool = False,
    skip_existing: bool = True,
) -> None:

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set. Add it to .env or export it.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    total_generated = 0
    total_skipped = 0
    errors = []

    for template_name in templates:
        template_id = f"{template_name}_v1"
        input_dir = INPUTS_DIR / template_name

        print(f"\n{'='*60}")
        print(f"Template: {template_id}")
        print(f"{'='*60}")

        # Load prompt template
        try:
            tmpl = load_prompt_template(template_name)
        except FileNotFoundError as e:
            print(f"  ERROR: {e}")
            continue

        system_prompt_raw = tmpl["system_prompt"]
        user_prompt_raw = tmpl["user_prompt_template"]

        # Load manifest
        try:
            manifest = load_manifest(input_dir)
        except FileNotFoundError:
            print(f"  ERROR: manifest.json not found in {input_dir}")
            continue

        # Process each input file
        for input_id, meta in sorted(manifest.items()):
            ref_path = output_path(template_name, input_id)

            # Skip if already generated
            if skip_existing and ref_path.exists():
                print(f"  SKIP  {input_id} (reference already exists)")
                total_skipped += 1
                continue

            # Load input text
            input_file = input_dir / f"{input_id}.txt"
            if not input_file.exists():
                print(f"  ERROR {input_id}: input file not found at {input_file}")
                errors.append(input_id)
                continue

            with open(input_file, encoding="utf-8") as f:
                input_text = f.read()

            # Build variables and render prompts
            variables = build_variables(input_id, meta, input_text)
            try:
                system_prompt = render_jinja(system_prompt_raw, variables)
                user_prompt   = render_jinja(user_prompt_raw,   variables)
            except Exception as e:
                print(f"  ERROR {input_id}: template rendering failed — {e}")
                errors.append(input_id)
                continue

            if dry_run:
                print(f"  DRY   {input_id} [{meta['language'].upper()}] "
                      f"— system: {len(system_prompt.split())} words, "
                      f"user: {len(user_prompt.split())} words")
                total_generated += 1
                continue

            # Call GPT-4o
            print(f"  GEN   {input_id} [{meta['language'].upper()}] ... ", end="", flush=True)
            try:
                reference_text = call_gpt4o(client, system_prompt, user_prompt)
                ref_path.write_text(reference_text, encoding="utf-8")
                print(f"done ({len(reference_text.split())} words → {ref_path.name})")
                total_generated += 1
                # Rate limit buffer: 1 second between calls
                time.sleep(1)
            except Exception as e:
                print(f"FAILED — {e}")
                errors.append(input_id)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Generated : {total_generated}")
    print(f"  Skipped   : {total_skipped}")
    print(f"  Errors    : {len(errors)}")
    if errors:
        print(f"  Failed IDs: {', '.join(errors)}")
    print(f"\nReference outputs saved to: {REFS_DIR}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate GPT-4o reference outputs for ROUGE evaluation."
    )
    parser.add_argument(
        "--template",
        choices=ROUGE_TEMPLATES + ["all"],
        default="all",
        help="Which template to generate references for (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be generated without calling the API",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Regenerate even if reference file already exists",
    )
    args = parser.parse_args()

    templates = ROUGE_TEMPLATES if args.template == "all" else [args.template]
    skip_existing = not args.no_skip

    if args.dry_run:
        print("DRY RUN — no API calls will be made\n")

    generate_references(
        templates=templates,
        dry_run=args.dry_run,
        skip_existing=skip_existing,
    )


if __name__ == "__main__":
    main()
