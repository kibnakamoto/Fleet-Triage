"""Self-contained HTML timeline: one SVG per signal with detected fault windows shaded."""
from html import escape

from .signals import SIGNALS

W, H = 900, 90
COLORS = {"ecu_loss": "#d6336c", "sensor_open": "#e8590c", "sensor_error": "#ae3ec9",
          "stuck_sensor": "#1c7ed6", "intermittent_wiring": "#f59f00", "ground_noise": "#0ca678"}

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#f6f7f8;--ink:#1b2430;--muted:#5b6876}}
@media (prefers-color-scheme:dark){{:root{{--bg:#11181d;--ink:#e6ecea;--muted:#9aa9b0}}}}
body{{margin:0;padding:24px;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}
h1{{font-size:1.3rem;margin:0 0 8px}} h2{{font-size:1rem;margin:20px 0 4px}} small{{color:var(--muted);font-weight:400}}
svg{{width:100%;max-width:900px;height:auto;display:block;border:1px solid var(--muted);border-radius:6px}}
ul{{list-style:none;padding:0;display:flex;gap:16px;flex-wrap:wrap}} li span{{display:inline-block;width:12px;height:12px;margin-right:6px;opacity:.6}}
</style></head><body>
<h1>{title}</h1><p>Shaded windows are detected faults; hover one for details. Time runs 0 to {total:.0f} s.</p>
<ul>{legend}</ul>
{blocks}
</body></html>
"""


def timeline_html(series, hyps, span, title="Fleet Triage timeline"):
    t0, t1 = span
    total = max(t1 - t0, 1e-9)
    blocks = []
    for sig in SIGNALS:
        pts = [(t, v) for t, _, v, err in series.get(sig.name, []) if not err]
        pts = pts[::max(1, len(pts) // 600)]
        lo = min((v for _, v in pts), default=0.0)
        hi = max((v for _, v in pts), default=1.0)
        if hi == lo:
            hi = lo + 1.0
        line = " ".join(f"{(t - t0) / total * W:.1f},{H - 6 - (v - lo) / (hi - lo) * (H - 12):.1f}" for t, v in pts)
        rects = "".join(
            f'<rect x="{(h.t0 - t0) / total * W:.1f}" y="0" width="{max((h.t1 - h.t0) / total * W, 1.5):.1f}" height="{H}" '
            f'fill="{COLORS[h.category]}" opacity="0.3"><title>{escape(h.category)} [{escape(h.scope)}] '
            f'{h.t0 - t0:.1f}s to {h.t1 - t0:.1f}s</title></rect>' for h in hyps if sig.name in h.signals)
        blocks.append(f'<section><h2>{escape(sig.name)} <small>{escape(sig.unit)}, {lo:.1f} to {hi:.1f}</small></h2>'
                      f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{escape(sig.name)} over time">{rects}'
                      f'<polyline points="{line}" fill="none" stroke="currentColor" stroke-width="1"/></svg></section>')
    used = sorted({h.category for h in hyps})
    legend = "".join(f'<li><span style="background:{COLORS[c]}"></span>{escape(c)}</li>' for c in used) or "<li>No anomalies found</li>"
    return PAGE.format(title=escape(title), total=total, legend=legend, blocks="\n".join(blocks))
