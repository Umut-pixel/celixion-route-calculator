"""Sea routes between waypoints, on top of searoute-py."""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from functools import lru_cache

import searoute as sr
from searoute.searoute import setup_M

from .geo import great_circle_nm
from .zones import eca_distance_nm, piracy_distance_nm

# Passages a caller may close. Kept explicit so a typo fails instead of being ignored.
AVOIDABLE_PASSAGES = frozenset(
    {
        "babalmandab",
        "bering",
        "bosporus",
        "chili",
        "gibraltar",
        "malacca",
        "ormuz",
        "panama",
        "south_africa",
        "suez",
        "sunda",
    }
)

# searoute closes the Northwest Passage only by default: passing any list drops that default, and a
# closed Suez then sends Istanbul -> Shanghai through the Arctic. It stays closed on every request.
ALWAYS_CLOSED = ("northwest",)

# Further than this from the sea network, a waypoint may be inland or mistyped. Many real ports are this far out:
# the network is coarse, so the warning asks for a check and does not say the point is wrong.
SNAP_WARNING_NM = 50.0

# searoute labels these edges with a passage although they only lead up to it. Ports that snap to them would count
# as being in the strait: Istanbul could not sail south with the Bosporus closed. Only the strait keeps its label.
APPROACH_EDGES = (
    ((28.977708, 40.971568), (28.995, 41.027893)),  # bosporus, Marmara end
    ((34.5, 27), (33.75, 27.9)),  # suez, Gulf of Suez
    ((33.75, 27.9), (32.6, 29.7)),
    ((-80, 7), (-79.5, 8.6)),  # panama, Pacific side
    ((-79.5, 8.6), (-79.494118, 8.796576)),
    ((-79.494118, 8.796576), (-79.585922, 8.992656)),
    ((-80, 9.75), (-79.900612, 9.208176)),  # panama, Caribbean side
    ((106.8, -5.2), (106.5793, -5.3345)),  # sunda, both ends
    ((104, -7), (105.4331, -6.230303)),
    ((56.4, 26.4), (56.547226, 26.511054)),  # ormuz, Gulf end
)


class RouteError(ValueError):
    """The request cannot produce a route."""


@dataclass(frozen=True)
class Point:
    lon: float
    lat: float


@dataclass(frozen=True)
class RouteLeg:
    distance_nm: float
    eca_nm: float
    piracy_nm: float
    passages: tuple[str, ...]
    coordinates: tuple[tuple[float, float], ...]
    warnings: tuple[str, ...]


@lru_cache(maxsize=1)
def prepare_network() -> None:
    """Clear the approach labels once. Each searoute call copies this graph shallowly, so the change carries over."""
    network = setup_M()
    for one, other in APPROACH_EDGES:
        # searoute stores each direction as its own edge.
        network.get_edge_data(one, other).pop("passage", None)
        network.get_edge_data(other, one).pop("passage", None)


def _in_frame(point: tuple[float, float], neighbour: tuple[float, float]) -> tuple[float, float]:
    """The point on the same turn of the world as its neighbour, since the line unrolls past +/-180."""
    return (point[0] + 360 * round((neighbour[0] - point[0]) / 360), point[1])


def closed_passages(avoid: list[str] | tuple[str, ...]) -> list[str]:
    unknown = sorted(set(avoid) - AVOIDABLE_PASSAGES)
    if unknown:
        raise RouteError(f"Unknown passage: {', '.join(map(ascii, unknown))}")
    return sorted(set(avoid) | set(ALWAYS_CLOSED))


def route_leg(origin: Point, destination: Point, avoid: list[str] | tuple[str, ...] = ()) -> RouteLeg:
    """One leg. The distance runs along the sea network, as searoute measures it; the line drawn also
    reaches the two points themselves."""
    prepare_network()
    start, end = (origin.lon, origin.lat), (destination.lon, destination.lat)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # a blocked route is reported below
        feature = sr.searoute(
            list(start),
            list(end),
            units="naut",
            restrictions=closed_passages(avoid),
            return_passages=True,
        )

    # A blocked route has no points at all. One point means both ends sit on the same network node.
    line = [tuple(point) for point in feature.geometry["coordinates"]]
    if not line:
        raise RouteError("No sea route between these points with the selected passages closed")

    notes = []
    for label, point, snapped in (("Origin", start, line[0]), ("Destination", end, line[-1])):
        gap = great_circle_nm(point, snapped)
        if gap > SNAP_WARNING_NM:
            notes.append(f"{label} is {gap:.0f} nm from the sea network. Check the location")

    # Two nearby ports can snap to one node, which measures zero miles along the network.
    apart_nm = great_circle_nm(start, end)
    shared_node = len(line) == 1 and apart_nm > 0
    if shared_node:
        notes.append("Both ends share one sea network point. The distance is a straight line, not a sea route")
    measured = [start, end] if shared_node else line
    distance_nm = round(apart_nm if shared_node else feature.properties["length"], 1)

    return RouteLeg(
        distance_nm=distance_nm,
        eca_nm=min(eca_distance_nm(measured), distance_nm),
        piracy_nm=min(piracy_distance_nm(measured), distance_nm),
        passages=tuple(sorted(feature.properties.get("traversed_passages") or ())),
        coordinates=(_in_frame(start, line[0]), *line, _in_frame(end, line[-1])),
        warnings=tuple(notes),
    )
