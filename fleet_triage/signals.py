"""Signal database: a small, simplified J1939-style set (illustrative, not the SAE tables)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    name: str
    pgn: int
    sa: int            # source address (which simulated ECU sends it)
    start: int         # first data byte (0-based)
    length: int        # bytes, little-endian
    scale: float
    offset: float
    period: float      # nominal transmit period, seconds
    unit: str
    noise: float       # nominal sensor noise sigma, physical units
    stuck_min_s: float  # a frozen value shorter than this is not reported

    @property
    def error_raw(self) -> int:
        return 0xFE if self.length == 1 else 0xFE00

    @property
    def valid_max(self) -> int:
        return 0xFA if self.length == 1 else 0xFAFF


SIGNALS = (
    Signal("engine_speed", 61444, 0x00, 3, 2, 0.125, 0.0, 0.05, "rpm", 6.0, 2.0),
    Signal("coolant_temp", 65262, 0x00, 0, 1, 1.0, -40.0, 1.0, "degC", 0.6, 15.0),
    Signal("oil_pressure", 65263, 0x00, 3, 1, 4.0, 0.0, 0.5, "kPa", 8.0, 8.0),
    Signal("battery_voltage", 65271, 0x1E, 4, 2, 0.05, 0.0, 1.0, "V", 0.12, 10.0),
)
BY_NAME = {s.name: s for s in SIGNALS}
BY_PGN_SA = {(s.pgn, s.sa): s for s in SIGNALS}
SA_NAMES = {0x00: "engine ECU", 0x1E: "body/electrical ECU"}
