import pytest

from fleet_triage import can, evaluate, replay, simulator, store, triage, viz
from fleet_triage.signals import SIGNALS


@pytest.mark.parametrize("sig", SIGNALS, ids=lambda s: s.name)
def test_encode_decode_roundtrip(sig):
    value = sig.offset + sig.scale * 100
    s, raw, decoded, err = can.decode(can.make_id(sig.pgn, sig.sa), can.encode(sig, can.raw_from_value(sig, value)))
    assert s is sig and not err
    assert abs(decoded - value) <= sig.scale / 2


def test_error_indicator_decodes_as_error():
    sig = SIGNALS[1]
    _, _, value, err = can.decode(can.make_id(sig.pgn, sig.sa), can.encode(sig, sig.error_raw))
    assert err and value is None


def test_candump_roundtrip(tmp_path):
    frames, _ = simulator.simulate(7, 20.0, [])
    path = tmp_path / "x.candump"
    can.write_candump(frames, path)
    back = can.read_candump(path)
    assert len(back) == len(frames)
    assert all(abs(a[0] - b[0]) < 1e-6 and a[1:] == b[1:] for a, b in zip(frames, back))


def test_replay_is_deterministic():
    faults = simulator.random_faults(11, 3)
    a, _ = simulator.simulate(11, 120.0, faults)
    b, _ = simulator.simulate(11, 120.0, faults)
    c, _ = simulator.simulate(12, 120.0, faults)
    assert a == b and a != c
    ha = [(h.category, h.scope, h.t0, h.t1) for h in triage.analyze(a)[0]]
    hb = [(h.category, h.scope, h.t0, h.t1) for h in triage.analyze(b)[0]]
    assert ha == hb


CASES = [
    ("dropout", dict(signal="oil_pressure"), "sensor_open", "oil_pressure"),
    ("intermittent", dict(signal="coolant_temp"), "intermittent_wiring", "coolant_temp"),
    ("stuck", dict(signal="engine_speed"), "stuck_sensor", "engine_speed"),
    ("noise", dict(signal="engine_speed"), "ground_noise", "engine_speed"),
    ("error_indicator", dict(signal="battery_voltage"), "sensor_error", "battery_voltage"),
    ("ecu_outage", dict(sa=0x00), "ecu_loss", "SA 0x00"),
]


@pytest.mark.parametrize("kind,kw,category,scope", CASES, ids=[c[0] for c in CASES])
def test_each_fault_is_found(kind, kw, category, scope):
    fault = simulator.Fault(kind, 40.0, 62.0, **kw)
    frames, _ = simulator.simulate(5, 120.0, [fault])
    hyps = triage.analyze(frames)[0]
    matches, fps, misses = evaluate.score_run(hyps, [fault])
    assert matches and not misses, [(h.category, h.scope, h.t0 - can.BASE_EPOCH, h.t1 - can.BASE_EPOCH) for h in hyps]
    assert not fps


def test_fault_free_logs_raise_no_alarms():
    for seed in range(40):
        frames, _ = simulator.simulate(seed, 120.0, [])
        assert triage.analyze(frames)[0] == []


def test_sql_health_view():
    frames, _ = simulator.simulate(1, 30.0, [])
    conn = store.open_db()
    store.ingest(conn, frames)
    rows = {r[0]: r for r in store.health(conn)}
    assert set(rows) == {s.name for s in SIGNALS}
    assert rows["engine_speed"][4] < 0.06  # max gap stays near the 50 ms period


def test_accuracy_floor_on_regression_seeds():
    """Guards against detector regressions; numbers measured at v0.1.0 with margin."""
    stats = evaluate.evaluate(range(0, 60))
    _, (tp, fp, fn) = evaluate.table(stats)
    assert tp / (tp + fp) >= 0.90
    assert tp / (tp + fn) >= 0.88


def _run(fault):
    frames, _ = simulator.simulate(5, 120.0, [fault])
    hyps, conn, sp = triage.analyze(frames)
    return hyps, store.load_series(conn), sp


def test_replay_snapshot_flags_stale_signal_and_active_fault():
    hyps, series, _ = _run(simulator.Fault("dropout", 40.0, 62.0, signal="oil_pressure"))
    mid = replay.snapshot(series, can.BASE_EPOCH + 50.0)
    assert mid["oil_pressure"]["stale"] and not mid["engine_speed"]["stale"]
    assert not replay.snapshot(series, can.BASE_EPOCH + 30.0)["oil_pressure"]["stale"]
    assert any(h.category == "sensor_open" and h.scope == "oil_pressure"
               for h in replay.active(hyps, can.BASE_EPOCH + 50.0))
    assert not replay.active(hyps, can.BASE_EPOCH + 100.0)


def test_html_timeline_is_deterministic_and_marks_faults():
    hyps, series, sp = _run(simulator.Fault("noise", 40.0, 62.0, signal="engine_speed"))
    page = viz.timeline_html(series, hyps, sp)
    assert page == viz.timeline_html(series, hyps, sp)
    assert "<svg" in page and "ground_noise" in page and page.count("<polyline") == len(SIGNALS)
