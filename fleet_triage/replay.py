"""Time-synchronized replay: the aligned state of every signal at any timestamp."""
import bisect

from .signals import SIGNALS


def snapshot(series, t_abs):
    """Last known sample of each signal at or before t_abs, with its age and a staleness flag."""
    out = {}
    for sig in SIGNALS:
        s = series.get(sig.name, [])
        i = bisect.bisect_right([x[0] for x in s], t_abs) - 1
        if i < 0:
            out[sig.name] = None
            continue
        t, raw, value, err = s[i]
        age = t_abs - t
        out[sig.name] = {"t": t, "raw": raw, "value": value, "error": err, "age": age,
                         "stale": age > max(3 * sig.period, 1.0), "unit": sig.unit}
    return out


def active(hyps, t_abs):
    """Hypotheses whose window contains t_abs."""
    return [h for h in hyps if h.t0 <= t_abs <= h.t1]


def render(snap, act, t_rel):
    lines = [f"STATE AT t = {t_rel:.1f} s", ""]
    for name, d in snap.items():
        if d is None:
            lines.append(f"  {name:<16} no data yet")
        elif d["error"]:
            lines.append(f"  {name:<16} ERROR INDICATOR (age {d['age']:.2f}s)")
        elif d["stale"]:
            lines.append(f"  {name:<16} STALE: last {d['value']:.1f} {d['unit']}, {d['age']:.1f}s ago")
        else:
            lines.append(f"  {name:<16} {d['value']:.1f} {d['unit']:<5} (age {d['age']:.2f}s)")
    lines += ["", "Active hypotheses: " + (", ".join(f"{h.category}[{h.scope}]" for h in act) or "none")]
    return "\n".join(lines)
