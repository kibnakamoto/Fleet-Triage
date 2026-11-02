import argparse
import json

from . import can, evaluate, simulator, triage


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fleet_triage", description="Triage root causes from CAN logs.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("simulate", help="write a candump log with injected faults")
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--duration", type=float, default=120.0)
    s.add_argument("--faults", type=int, default=2, help="number of random faults (0-3)")
    s.add_argument("--out", default="run.candump")
    t = sub.add_parser("triage", help="analyze a candump log")
    t.add_argument("log")
    t.add_argument("--json", action="store_true")
    e = sub.add_parser("evaluate", help="score against injected ground truth")
    e.add_argument("--runs", type=int, default=200)
    e.add_argument("--seed0", type=int, default=0)
    a = ap.parse_args(argv)

    if a.cmd == "simulate":
        faults = simulator.random_faults(a.seed, a.faults)
        frames, truth = simulator.simulate(a.seed, a.duration, faults)
        can.write_candump(frames, a.out)
        with open(a.out + ".truth.json", "w") as f:
            json.dump(truth, f, indent=2)
        print(f"wrote {len(frames)} frames to {a.out} (truth: {a.out}.truth.json)")
    elif a.cmd == "triage":
        hyps, conn, sp = triage.analyze(can.read_candump(a.log))
        if a.json:
            print(json.dumps([{"category": h.category, "scope": h.scope, "t0": round(h.t0 - sp[0], 3),
                               "t1": round(h.t1 - sp[0], 3)} for h in hyps], indent=2))
        else:
            print(triage.render(hyps, conn, sp))
    else:
        seeds = range(a.seed0, a.seed0 + a.runs)
        tbl, _ = evaluate.table(evaluate.evaluate(seeds))
        fa, hours = evaluate.false_alarms(range(a.seed0 + 100000, a.seed0 + 100000 + a.runs))
        print(tbl)
        print(f"\nFault-free logs: {fa} false alarms over {hours:.2f} h of log")


if __name__ == "__main__":
    main()
