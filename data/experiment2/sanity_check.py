# Re-run full verification
import json, sys
sys.path.insert(0, ".")
from modules.governance.ethics_auditor import EthicsAuditor

with open("./data/experiment2/ethics_corpus.json") as f:
    corpus = json.load(f)

auditor = EthicsAuditor(llm_client=None)
TEMPLATE_LIMITS = {
    "meeting_minutes_v1":         {"min": 150, "max": 800},
    "document_summarizer_v1":     {"min":  80, "max": 350},
    "lecture_generator_v1":       {"min": 400, "max": 1200},
    "curriculum_designer_v1":     {"min": 300, "max": 1000},
    "collaboration_framework_v1": {"min": 300, "max": 900},
}
tp = tn = fp = fn = 0
errors = []
for e in corpus:
    lim = TEMPLATE_LIMITS[e["template_id"]]
    result = auditor.evaluate(
        output_text=e["output_text"],
        template_id=e["template_id"],
        language=e["language"],
        min_words=lim["min"],
        max_words=lim["max"],
    )
    is_blocking = e["violation_type"] in ("EC-06", "EC-07")
    predicted_block = not result.passed
    if is_blocking and predicted_block:           tp += 1
    elif not is_blocking and not predicted_block: tn += 1
    elif not is_blocking and predicted_block:
        fp += 1
        errors.append(f"FP: {e['entry_id']} ({e['violation_type']}) — {result.failed_checks}")
    else:
        fn += 1
        errors.append(f"FN: {e['entry_id']} ({e['violation_type']})")
    if e["violation_type"] in ("EC-03", "EC-04"):
        found = any(e["violation_type"] in w for w in result.warnings)
        if not found:
            errors.append(f"MISSED WARNING: {e['entry_id']} ({e['violation_type']}) — {result.warnings}")

print(f"Blocking: TP={tp} TN={tn} FP={fp} FN={fn}")
precision = tp/(tp+fp) if (tp+fp) else 0
recall    = tp/(tp+fn) if (tp+fn) else 0
print(f"Precision={precision:.2f}  Recall={recall:.2f}")
print(f"Errors: {len(errors)}")
for err in errors:
    print(f"  {err}")
