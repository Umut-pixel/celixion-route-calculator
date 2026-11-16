"""Time at sea and port calls. Pure arithmetic, no routing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class PortCall:
    arrival: datetime | None
    departure: datetime | None


def sea_days(distance_nm: float, speed_knots: float, sea_margin_pct: float = 0.0) -> float:
    """Sailing time in days. The sea margin stretches it for weather, current and routing."""
    if speed_knots <= 0:
        raise ValueError("Speed must be above zero")
    if sea_margin_pct < 0:
        raise ValueError("Sea margin cannot be negative")
    return distance_nm / (speed_knots * 24) * (1 + sea_margin_pct / 100)


def port_calls(start: datetime | None, days_in_port: list[float], leg_sea_days: list[float]) -> list[PortCall]:
    """Arrival and departure at each port, starting with the arrival at the first one."""
    if len(days_in_port) != len(leg_sea_days) + 1:
        raise ValueError("A voyage needs exactly one more port than legs")
    if start is None:
        return [PortCall(None, None) for _ in days_in_port]

    calls = []
    clock = start
    for index, days in enumerate(days_in_port):
        departure = clock + timedelta(days=days)
        calls.append(PortCall(clock, departure))
        if index < len(leg_sea_days):
            clock = departure + timedelta(days=leg_sea_days[index])
    return calls
