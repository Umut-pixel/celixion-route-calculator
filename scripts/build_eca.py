"""Build sea_route/data/eca.geojson.

Usage: python scripts/build_eca.py <eca_reg14_sox_pm.geojson>

The input is the Marine Regions layer MarineRegions:eca_reg14_sox_pm (Flanders Marine Institute, CC-BY 4.0). It
predates the Mediterranean ECA, which is added here from MARPOL Annex VI, appendix VII (MEPC.361(79)).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import Polygon, mapping, shape
from shapely.ops import unary_union

OUTPUT = Path(__file__).resolve().parent.parent / "sea_route" / "data" / "eca.geojson"
SIMPLIFY_DEGREES = 0.02  # about one nautical mile


def dms(degrees: float, minutes: float) -> float:
    return degrees + minutes / 60


CAPE_TRAFALGAR = (-dms(6, 2), dms(36, 11))
CAPE_SPARTEL = (-dms(5, 55), dms(35, 48))
MEHMETCIK_BURNU = (dms(26, 11), dms(40, 3))
KUMKALE_BURNU = (dms(26, 12), dms(40, 1))

SUEZ_EXCLUSION = [
    (dms(32, 16), dms(31, 29)),
    (dms(32, 28.48), dms(31, 29)),
    (dms(32, 32.62), dms(31, 14)),
    (dms(32, 16), dms(31, 14)),
]

# The legal limits are the two lines above and the Suez exclusion; everywhere else the area ends at the coast.
# These points run over land, clear of the coast, so that only those limits decide what is in or out.
MEDITERRANEAN_OUTLINE = [
    CAPE_TRAFALGAR,
    CAPE_SPARTEL,
    (-5.6, 35.0), (-2.0, 34.2), (10.0, 33.0), (13.0, 32.2), (15.0, 31.4), (19.0, 29.9), (25.0, 30.5), (29.0, 30.4),
    (32.0, 30.9),
    SUEZ_EXCLUSION[3],
    SUEZ_EXCLUSION[2],
    (32.7, 31.0), (33.5, 30.9), (34.6, 31.0), (35.5, 33.0), (36.4, 35.0), (36.8, 37.0), (34.0, 37.3), (31.0, 37.5),
    (29.0, 37.5), (28.5, 37.5), (27.6, 38.6), (27.0, 39.9),
    KUMKALE_BURNU,
    MEHMETCIK_BURNU,
    # Along the Gallipoli peninsula, which keeps the Gulf of Saros in and the Dardanelles out.
    (26.27, 40.15), (26.42, 40.30), (26.72, 40.52), (26.85, 40.60),
    (26.9, 41.1), (24.0, 42.0), (20.5, 42.0), (18.5, 44.0), (15.5, 46.2), (12.0, 46.5), (8.0, 45.5), (4.5, 44.5),
    (1.0, 43.0), (-2.0, 40.0), (-5.5, 37.5),
]


def mediterranean() -> Polygon:
    return Polygon(MEDITERRANEAN_OUTLINE).difference(Polygon(SUEZ_EXCLUSION))


def main(source: str) -> None:
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    areas: dict[str, list] = {}
    for feature in data["features"]:
        name = feature["properties"]["area"].removesuffix(" area")
        name = "North American" if name.startswith("North American") else name
        areas.setdefault(name, []).append(shape(feature["geometry"]).buffer(0))

    features = [
        {
            "type": "Feature",
            "properties": {"area": name, "source": "Marine Regions, Flanders Marine Institute (CC-BY 4.0)"},
            "geometry": mapping(unary_union(shapes).simplify(SIMPLIFY_DEGREES)),
        }
        for name, shapes in sorted(areas.items())
    ]
    features.append(
        {
            "type": "Feature",
            "properties": {"area": "Mediterranean Sea", "source": "MARPOL Annex VI, appendix VII (MEPC.361(79))"},
            "geometry": mapping(mediterranean()),
        }
    )

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    main(sys.argv[1])
