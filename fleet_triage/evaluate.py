"""Score the triage pipeline against injected ground truth."""
from statistics import median

from . import can, triage
from .simulator import random_faults, simulate

TRUTH_CATEGORY = {"dropout": "sensor_open", "intermittent": "intermittent_wiring", "stuck": "stuck_sensor",
                  "noise": "ground_noise", "error_indicator": "sensor_error", "ecu_outage": "ecu_loss"}


def _iou(a0, a1, b0, b1):
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    union = max(a1, b1) - min(a0, b0)
    return inter / union if union > 0 else 0.0


def score_run(hyps, faults):
    """Greedy one-to-one matching. Returns (matches, false_positives, misses)."""
    free, matches, misses = list(hyps), [], []
    for f in faults:
        best = None
        for h in free:
            if h.category == TRUTH_CATEGORY[f.kind] and h.scope == f.scope:
                iou = _iou(h.t0 - can.BASE_EPOCH, h.t1 - can.BASE_EPOCH, f.t0, f.t1)
                if iou >= 0.5 and (best is None or iou > best[0]):
                    best = (iou, h)
        if best:
            free.remove(best[1])
            matches.append((f, best[1]))
        else:
            misses.append(f)
    return matches, free, misses


def evaluate(seeds, n_faults=(1, 2, 3), duration=120.0):
    stats = {c: {"tp": 0, "fp": 0, "fn": 0, "start_err": [], "end_err": []} for c in triage.PRIORITY}
    for seed in seeds:
        faults = random_faults(seed, n_faults[seed % len(n_faults)])
        frames, _ = simulate(seed, duration, faults)
        hyps, _, _ = triage.analyze(frames)
        matches, fps, misses = score_run(hyps, faults)
        for f, h in matches:
            s = stats[TRUTH_CATEGORY[f.kind]]
            s["tp"] += 1
            s["start_err"].append(abs(h.t0 - can.BASE_EPOCH - f.t0))
            s["end_err"].append(abs(h.t1 - can.BASE_EPOCH - f.t1))
        for f in misses:
            stats[TRUTH_CATEGORY[f.kind]]["fn"] += 1
        for h in fps:
            stats[h.category]["fp"] += 1
    return stats


def false_alarms(seeds, duration=120.0):
    total = 0
    for seed in seeds:
        frames, _ = simulate(seed, duration, [])
        total += len(triage.analyze(frames)[0])
    return total, len(list(seeds)) * duration / 3600


def table(stats):
    rows = ["| Root cause | Injected | Precision | Recall | Median start error (s) |", "|---|---|---|---|---|"]
    TP = FP = FN = 0
    for c in triage.PRIORITY:
        s = stats[c]
        n = s["tp"] + s["fn"]
        p = s["tp"] / (s["tp"] + s["fp"]) if s["tp"] + s["fp"] else float("nan")
        r = s["tp"] / n if n else float("nan")
        se = f"{median(s['start_err']):.2f}" if s["start_err"] else "n/a"
        rows.append(f"| {c} | {n} | {p:.2f} | {r:.2f} | {se} |")
        TP, FP, FN = TP + s["tp"], FP + s["fp"], FN + s["fn"]
    rows.append(f"| **all** | {TP + FN} | {TP / (TP + FP):.2f} | {TP / (TP + FN):.2f} | |")
    return "\n".join(rows), (TP, FP, FN)
