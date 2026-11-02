# Fleet Triage

Replayable CAN-telemetry triage. It ingests standard `candump` logs, decodes J1939-style signals into SQLite, runs per-signal anomaly detectors, and prints a **ranked list of likely root causes with a suggested next check**. A fault-injection simulator and an evaluation harness score the whole pipeline against ground truth.

The fault types come from debugging test-bench instrumentation: dropped sensor frames, frozen readings, noisy grounds and intermittent connectors. The question it answers is the one a field technician asks first: *what is wrong, and what do I check first?*

## Quick start

No dependencies beyond Python 3.10+ (tests need `pytest`).

```bash
python -m fleet_triage simulate --seed 3 --faults 2 --out run.candump
python -m fleet_triage triage run.candump
python -m fleet_triage replay run.candump --at 45      # aligned state of every signal at t = 45 s
python -m fleet_triage report run.candump --html timeline.html   # self-contained timeline
python -m fleet_triage evaluate --runs 200 --seed0 5000
pytest
```

Sample output (`run.candump.truth.json` holds the injected faults: noise on `oil_pressure` at 13.0 to 32.1 s, a frozen `engine_speed` at 56.9 to 70.0 s):

```
FLEET TRIAGE REPORT
Signal health (from SQL view):
  battery_voltage  n=120   errors=0    mean=27.6      max_gap=1.02s
  engine_speed     n=2400  errors=0    mean=1271.11   max_gap=0.05s
  ...
1. stuck_sensor  [engine_speed]  t=56.8s to 69.9s (13.1s)
   next: Value frozen while the bus is alive: suspect a failed sensor or latched output; compare with a reference.
2. ground_noise  [oil_pressure]  t=13.7s to 29.7s (16.0s)
   next: Signal is noisy: check ground and shield terminations, routing near high-current cables, supply ripple.
```

## Replay and timeline

- **`replay --at T`** reconstructs the time-synchronized state at any timestamp: the last known value of every signal, how old it is, whether it has gone stale, and which fault hypotheses are active. Same log in, same state out.
- **`report --html`** writes one self-contained page: a plot per signal with the detected fault windows shaded and hover details, no server or dependencies needed.

## Results

200 random scenarios (1 to 3 faults each, 120 s logs) on **held-out seeds 5000 to 5199**. Detector thresholds were tuned only on seeds 0 to 199. A hypothesis counts as correct when its category and scope (signal or source address) match an injected fault and the time intervals overlap with IoU >= 0.5.

| Root cause | Injected | Precision | Recall | Median start error (s) |
|---|---|---|---|---|
| ecu_loss | 63 | 1.00 | 1.00 | 0.49 |
| sensor_open | 76 | 0.99 | 1.00 | 0.23 |
| sensor_error | 61 | 1.00 | 1.00 | 0.22 |
| stuck_sensor | 69 | 1.00 | 0.90 | 0.28 |
| intermittent_wiring | 69 | 0.99 | 0.99 | 0.43 |
| ground_noise | 62 | 0.88 | 0.95 | 0.40 |
| **all** | 400 | 0.97 | 0.97 | |

Fault-free logs: **0 false alarms over 6.67 hours** of simulated log.

All 7 stuck-sensor misses are on the slow 1 Hz coolant signal, where the detector needs a value frozen for 15 s; shorter freezes are ignored by design.

## How it works

```
simulate / candump file -> decode (signal DB) -> SQLite (samples + SQL views)
        -> detectors (dropout, intermittent, stuck, noise, error)
        -> triage rules (e.g. several signals from one ECU vanish together = ecu_loss)
        -> ranked hypotheses + next checks        evaluate: score against injected truth
```

| Injected fault | Models | Detector | Root cause reported |
|---|---|---|---|
| dropout | unplugged sensor, open circuit | gap larger than 8 periods | sensor_open |
| ecu_outage | ECU power or ground loss | simultaneous dropouts on one source address | ecu_loss |
| intermittent | bad connector or crimp | cluster of short gaps | intermittent_wiring |
| stuck | frozen sensor or latched output | unchanged raw value for N seconds | stuck_sensor |
| noise | poor grounding or EMI | clusters of outsized second differences | ground_noise |
| error_indicator | ECU reports an error value | run of error-coded frames | sensor_error |

- **Replay is deterministic.** Same seed and faults give a byte-identical log, and the same log gives identical hypotheses (tested).
- **Standard formats.** Logs are SocketCAN `candump -L` text, so real captures can be fed to `triage`.
- **SQL, not just Python.** Signal health and maximum gaps come from SQL views using window functions.

## Limitations

- **Simulated data only.** The simulator and the detectors are written by the same person, so the table measures self-consistency, not field performance. Nothing here has run on a real fleet.
- **Simplified J1939.** Four signals with illustrative layouts; no transport protocol, address claiming or DBC loading.
- Faults are 10 to 25 s long; very short events are out of scope.
- Noise detection is the weakest category (precision 0.88).

## Roadmap

1. Load real DBC files and real logs.
2. An agent layer that uses the same SQL views as tools, records every model call for deterministic replay, and is scored by the same evaluation harness.
3. A Postgres backend and a timeline viewer in TypeScript.
