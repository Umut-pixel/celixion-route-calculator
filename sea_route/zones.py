"""How far a route runs inside an Emission Control Area or a piracy risk area."""
from __future__ import annotations

import json
import threading
from functools import lru_cache
from importlib.resources import files
from typing import Sequence

import numpy as np
import shapely
from shapely.geometry import LineString, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .geo import great_circle_nm

# GEOS crashes when threads share a prepared geometry, so its predicates run one at a time. Not optional: FastAPI
# runs these handlers in a thread pool.
_prepared_lock = threading.Lock()


def _load_area(filename: str) -> BaseGeometry:
    data = json.loads(files("sea_route.data").joinpath(filename).read_text(encoding="utf-8"))
    area = unary_union([shape(feature["geometry"]) for feature in data["features"]])
    shapely.prepare(area)
    return area


@lru_cache(maxsize=1)
def eca_area() -> BaseGeometry:
    return _load_area("eca.geojson")


@lru_cache(maxsize=1)
def piracy_area() -> BaseGeometry:
    return _load_area("piracy.geojson")


def _unbroken_stretches(line: Sequence[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """Split where a route crosses the antimeridian, so no segment runs the long way round the world.

    searoute unrolls longitudes past +/-180 on Pacific routes, so they are wrapped first. No zone reaches the
    antimeridian, so the one segment dropped at the crossing loses nothing.
    """
    line = [((lon + 180) % 360 - 180, lat) for lon, lat in line]
    stretches = [[line[0]]]
    for previous, point in zip(line, line[1:]):
        if abs(point[0] - previous[0]) > 180:
            stretches.append([])
        stretches[-1].append(point)
    return [stretch for stretch in stretches if len(stretch) > 1]


def _length_nm(geometry: BaseGeometry) -> float:
    parts = getattr(geometry, "geoms", [geometry])
    total = 0.0
    for part in parts:
        if isinstance(part, LineString):
            coords = list(part.coords)
            total += sum(great_circle_nm(a, b) for a, b in zip(coords, coords[1:]))
    return total


def _distance_inside_nm(line: Sequence[tuple[float, float]], area: BaseGeometry) -> float:
    if len(line) < 2:
        return 0.0
    segments = np.array([LineString(pair) for part in _unbroken_stretches(line) for pair in zip(part, part[1:])])
    if len(segments) == 0:
        return 0.0
    # Only segments crossing a zone's edge need the slow overlay; most are wholly in or wholly out.
    with _prepared_lock:
        touching = segments[shapely.intersects(area, segments)]
        inside = shapely.contains(area, touching)
    pieces = [*touching[inside], *shapely.intersection(touching[~inside], area)]
    return round(sum((_length_nm(piece) for piece in pieces), 0.0), 1)


def eca_distance_nm(line: Sequence[tuple[float, float]]) -> float:
    """Nautical miles of the line inside any ECA."""
    return _distance_inside_nm(line, eca_area())


def piracy_distance_nm(line: Sequence[tuple[float, float]]) -> float:
    """Nautical miles of the line inside a piracy risk area. Indicative: see the README."""
    return _distance_inside_nm(line, piracy_area())
