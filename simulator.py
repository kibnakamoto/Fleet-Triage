"""Seeded CAN traffic generator with reproducible fault injection."""
import math
import random
from dataclasses import dataclass, asdict

from . import can
from .signals import SIGNALS, BY_NAME

FAULT_KINDS = ("dropout", "intermittent", "stuck", "noise", "error_indicator", "ecu_outage")
NOISE_MULT = 8.0       # injected noise sigma = NOISE_MULT x nominal sigma
INTERMITTENT_P = 0.4   # probability a frame is lost inside an intermittent fault


@dataclass
class Fault:
    kind: str
    t0: float
    t1: float
    signal: str = ""   # signal name (single-signal faults)
    sa: int = -1       # source address (ecu_outage)

    @property
    def scope(self) -> str:
        return f"SA 0x{self.sa:02X}" if self.kind == "ecu_outage" else self.signal


def nominal(name: str, t: float) -> float:
    if name == "engine_speed":
        return 1200 + 600 * math.sin(2 * math.pi * t / 40) + 150 * math.sin(2 * math.pi * t / 7)
    if name == "coolant_temp":
        return 40 + 50 * (1 - math.exp(-t / 60))
    if name == "oil_pressure":
        return 100 + 0.1 * nominal("engine_speed", t)
    return 27.6 + 0.2 * math.sin(2 * math.pi * t / 25)  # battery_voltage


def _samples(seed, sig, duration):
    rng = random.Random(f"{seed}:{sig.name}")
    out, k = [], 0
    phase = rng.random() * sig.period
    while True:
        t = phase + k * sig.period + rng.uniform(-0.01, 0.01) * sig.period
        if t >= duration:
            return out, rng
        out.append([t, nominal(sig.name, t) + rng.gauss(0, sig.noise), False])
        k += 1


def _apply(samples, rng, sig, f):
    inside = [s for s in samples if f.t0 <= s[0] <= f.t1]
    inside_ids = {id(s) for s in inside}
    if f.kind in ("dropout", "ecu_outage"):
        return [s for s in samples if id(s) not in inside_ids]
    if f.kind == "intermittent":
        keep = {id(s) for s in inside if rng.random() >= INTERMITTENT_P}
        return [s for s in samples if id(s) not in inside_ids or id(s) in keep]
    if f.kind == "stuck":
        before = [s for s in samples if s[0] < f.t0]
        frozen = before[-1][1] if before else (inside[0][1] if inside else 0.0)
        for s in inside:
            s[1] = frozen
    elif f.kind == "noise":
        for s in inside:
            s[1] += rng.gauss(0, NOISE_MULT * sig.noise)
    elif f.kind == "error_indicator":
        for s in inside:
            s[2] = True
    return samples


def simulate(seed: int, duration: float = 120.0, faults=()):
    """Return (frames, truth). frames: [(t_abs, can_id, data)] sorted by time."""
    frames = []
    for sig in SIGNALS:
        samples, rng = _samples(seed, sig, duration)
        for f in faults:
            if (f.kind == "ecu_outage" and f.sa == sig.sa) or f.signal == sig.name:
                samples = _apply(samples, rng, sig, f)
        for t, v, err in samples:
            raw = sig.error_raw if err else can.raw_from_value(sig, v)
            frames.append((can.BASE_EPOCH + t, can.make_id(sig.pgn, sig.sa), can.encode(sig, raw)))
    frames.sort(key=lambda fr: (fr[0], fr[1]))
    return frames, [asdict(f) for f in faults]


def random_faults(seed: int, n: int):
    """n non-overlapping faults placed in separate time slots (10-25 s long)."""
    rng = random.Random(f"faults:{seed}")
    slots = [(10, 40), (45, 75), (80, 110)]
    rng.shuffle(slots)
    faults = []
    for lo, hi in slots[:n]:
        kind = rng.choice(FAULT_KINDS)
        dur = rng.uniform(10, 25)
        t0 = rng.uniform(lo, hi - dur)
        if kind == "ecu_outage":
            faults.append(Fault(kind, t0, t0 + dur, sa=0x00))
        else:
            faults.append(Fault(kind, t0, t0 + dur, signal=rng.choice(list(BY_NAME))))
    return faults
