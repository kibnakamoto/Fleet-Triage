"""Turn detector findings into ranked root-cause hypotheses."""
from dataclasses import dataclass, field

from . import store
from .detect import detect

PRIORITY = ["ecu_loss", "sensor_open", "sensor_error", "stuck_sensor", "intermittent_wiring", "ground_noise"]
KIND_TO_CATEGORY = {"dropout": "sensor_open", "intermittent": "intermittent_wiring",
                    "stuck": "stuck_sensor", "noise": "ground_noise", "error": "sensor_error"}
ACTIONS = {
    "ecu_loss": "Check ECU supply, ground and connector; all signals from this source address vanished together.",
    "sensor_open": "Inspect the sensor connector and harness for an open circuit; other signals on the ECU stayed alive.",
    "sensor_error": "ECU is reporting an error indicator: check sensor supply and signal wiring, read stored fault codes.",
    "stuck_sensor": "Value frozen while the bus is alive: suspect a failed sensor or latched output; compare with a reference.",
    "intermittent_wiring": "Frames drop in bursts: wiggle-test connectors, check crimps and shield terminations, look for chafing.",
    "ground_noise": "Signal is noisy: check ground and shield terminations, routing near high-current cables, supply ripple.",
}


@dataclass
class Hypothesis:
    category: str
    scope: str
    t0: float
    t1: float
    signals: list = field(default_factory=list)

    @property
    def duration(self):
        return self.t1 - self.t0


def _overlap(a, b):
    ov = min(a.t1, b.t1) - max(a.t0, b.t0)
    return ov >= 0.5 * min(a.t1 - a.t0, b.t1 - b.t0)


def hypotheses(findings):
    out, drops = [], [f for f in findings if f.kind == "dropout"]
    used = set()
    for sa in sorted({f.sa for f in drops}):
        group = [f for f in drops if f.sa == sa]
        for f in group:
            comp = [g for g in group if _overlap(f, g)]
            if len({g.signal for g in comp}) >= 2 and not used.intersection(id(g) for g in comp):
                used.update(id(g) for g in comp)
                out.append(Hypothesis("ecu_loss", f"SA 0x{sa:02X}", min(g.t0 for g in comp),
                                      max(g.t1 for g in comp), sorted(g.signal for g in comp)))
    for f in findings:
        if id(f) not in used:
            out.append(Hypothesis(KIND_TO_CATEGORY[f.kind], f.signal, f.t0, f.t1, [f.signal]))
    out.sort(key=lambda h: (PRIORITY.index(h.category), -h.duration, h.t0))
    return out


def analyze(frames, conn=None):
    conn = conn or store.open_db()
    store.ingest(conn, frames)
    sp = store.span(conn)
    return hypotheses(detect(store.load_series(conn), sp)), conn, sp


def render(hyps, conn, sp):
    t0 = sp[0]
    lines = ["FLEET TRIAGE REPORT", "=" * 19, "", "Signal health (from SQL view):"]
    for name, n, errs, mean, gap in store.health(conn):
        lines.append(f"  {name:<16} n={n:<5} errors={errs:<4} mean={mean:<9} max_gap={gap or 0:.2f}s")
    lines += ["", f"{len(hyps)} hypothesis(es), most urgent first:", ""]
    for i, h in enumerate(hyps, 1):
        lines.append(f"{i}. {h.category}  [{h.scope}]  t={h.t0 - t0:.1f}s to {h.t1 - t0:.1f}s ({h.duration:.1f}s)")
        lines.append(f"   next: {ACTIONS[h.category]}")
    if not hyps:
        lines.append("No anomalies found.")
    return "\n".join(lines)
