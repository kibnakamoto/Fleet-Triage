"""Per-signal anomaly detectors. Each returns Findings with absolute-time intervals."""
from dataclasses import dataclass
from statistics import median

from .signals import SIGNALS


@dataclass
class Finding:
    kind: str    # dropout | intermittent | stuck | noise | error
    signal: str
    sa: int
    t0: float
    t1: float


def _cluster(items, sep):
    """Group sorted (t0, t1) items whose start is within `sep` of the previous end."""
    groups = []
    for a, b in items:
        if groups and a - groups[-1][-1][1] <= sep:
            groups[-1].append((a, b))
        else:
            groups.append([(a, b)])
    return groups


def detect(series, span):
    lo, hi = span
    out = []
    for sig in SIGNALS:
        s = series.get(sig.name, [])
        P = sig.period
        if not s:
            out.append(Finding("dropout", sig.name, sig.sa, lo, hi))
            continue
        ts = [x[0] for x in s]
        drop_thr, short_thr = max(8 * P, 2.0), 1.8 * P

        # --- dropouts and intermittent gaps -------------------------------------------
        for a, b in ((lo, ts[0]), (ts[-1], hi)):
            if b - a >= drop_thr:
                out.append(Finding("dropout", sig.name, sig.sa, a, b))
        shorts = []
        for a, b in zip(ts, ts[1:]):
            if b - a >= drop_thr:
                out.append(Finding("dropout", sig.name, sig.sa, a, b))
            elif b - a > short_thr:
                shorts.append((a, b))
        for g in _cluster(shorts, max(8 * P, 3.0)):
            if len(g) >= 3:
                out.append(Finding("intermittent", sig.name, sig.sa, g[0][0], g[-1][1]))

        # --- frozen value ------------------------------------------------------------------
        good = [x for x in s if not x[3]]
        i = 0
        while i < len(good):
            j = i
            while j + 1 < len(good) and good[j + 1][1] == good[i][1] and good[j + 1][0] - good[j][0] < drop_thr:
                j += 1
            if good[j][0] - good[i][0] >= sig.stuck_min_s:
                out.append(Finding("stuck", sig.name, sig.sa, good[i][0], good[j][0]))
            i = j + 1

        # --- noise: clusters of outsized second differences (cancels slow trends) ----
        d2 = [(b[0], abs(c[2] - 2 * b[2] + a[2])) for a, b, c in zip(good, good[1:], good[2:])
              if c[0] - a[0] < 4.5 * P]
        if len(d2) > 10:
            base = max(1.4826 * median(d for _, d in d2), 0.6 * sig.scale)
            flagged = [(t, t) for t, d in d2 if d > 4 * base]
            for g in _cluster(flagged, 12 * P):
                if len(g) >= 4 and g[-1][1] - g[0][0] >= 3.0:
                    out.append(Finding("noise", sig.name, sig.sa, g[0][0], g[-1][1]))

        # --- error indicators ------------------------------------------------------------
        run = []
        for t, _, _, err in s + [(0, 0, 0, False)]:
            if err:
                run.append(t)
            else:
                if len(run) >= 3:
                    out.append(Finding("error", sig.name, sig.sa, run[0], run[-1]))
                run = []
    return out
