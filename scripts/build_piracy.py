"""Build sea_route/data/piracy.geojson.

Usage: python scripts/build_piracy.py

Every limit below is a Joint War Committee (JWC) line. The JWC is a joint committee of the Lloyd's Market Association
and the International Underwriting Association. Its circulars, read on 4 November 2026:

  JWLA-032, 18 December 2023  https://lmalloyds.com/wp-content/uploads/2025/08/JWLA-032-Guyana-1.pdf
  JWLA-033, 3 March 2026      https://lmalloyds.com/wp-content/uploads/2026/03/JWLA-033_Iran.pdf
  JWLA-034, 29 July 2026      https://lmalloyds.com/wp-content/uploads/2025/06/JWLA-034-Saudi-Arabia.pdf
  JWLA-035, 16 September 2026 https://lmalloyds.com/wp-content/uploads/2026/09/JWLA-035-Black-Sea.pdf

The JWC lists areas for hull war, piracy, terrorism and related perils together and gives no reason for any one of
them. Which areas count as piracy is this project's choice, not the JWC's:

  Counted
    Indian Ocean, Gulf of Aden and Southern Red Sea, with the limits it had as its own entry in JWLA-032.
    Gulf of Guinea, the same in all four circulars.

  Left out
    Persian Gulf, Gulf of Oman and the Arabian Sea out to 65E. JWLA-032 lists the Gulf as a separate entry. JWLA-033,
      the Iran revision, merged it into the Indian Ocean entry and moved the limit to the Pakistan coast. Counting
      that whole entry would call a voyage from Fujairah to Ras Tanura a piracy transit.
    Red Sea between 18N and 25.5N. Added by JWLA-034. The circular gives no reason and nothing read here ties it to
      piracy.
    Cabo Delgado. Defined as a territorial sea, which needs a baseline these two lines do not give.
    Black Sea and Sea of Azov. Nothing read here ties them to piracy.
    Countries listed by name. They have no limits to draw beyond their coastal waters. Somalia, Djibouti, Yemen,
      Nigeria, Benin and Togo are covered where their waters lie inside the two areas counted.

Both areas counted lie inside the entries of the list in force (JWLA-035). The Gulf of Guinea limits are on that list
as they stand. Two Indian Ocean limits are not: 18N, and the northeast limit from the Yemen border to 10 48N 60 15E.
"""
from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import Polygon, mapping

OUTPUT = Path(__file__).resolve().parent.parent / "sea_route" / "data" / "piracy.geojson"


def dms(degrees: float, minutes: float = 0, seconds: float = 0) -> float:
    return degrees + minutes / 60 + seconds / 3600


# JWLA-032. The last three points are still on JWLA-035. RED_SEA_LIMIT left the list with JWLA-034, and YEMEN_BORDER and
# NORTHEAST_HIGH_SEAS with JWLA-033.
RED_SEA_LIMIT = 18.0
YEMEN_BORDER = (dms(53, 6.5), dms(16, 38.5))
NORTHEAST_HIGH_SEAS = (dms(53, 50), dms(14, 55))
EAST_HIGH_SEAS = (dms(60, 15), dms(10, 48))
SOUTH_HIGH_SEAS = (dms(48, 45), -dms(6, 45))
SOMALIA_BORDER = (dms(41, 34), -dms(1, 40))

# JWLA-032 to JWLA-035, word for word the same.
TOGO_COAST = (dms(1, 12), dms(6, 6, 45))
GUINEA_HIGH_SEAS = (dms(3), -dms(0, 40))
CAPE_LOPEZ = (dms(8, 42), -dms(0, 40))

# Both entries read "the waters enclosed by" these limits, so everywhere else the area ends at the coast. As in
# build_eca.py, the other points run over land, clear of the coast, so that only the JWC limits decide what is in or
# out. They are not JWC coordinates.
INDIAN_OCEAN_OUTLINE = [
    (37.5, RED_SEA_LIMIT),
    (48.0, RED_SEA_LIMIT),
    (52.8, 17.2),
    YEMEN_BORDER,
    NORTHEAST_HIGH_SEAS,
    EAST_HIGH_SEAS,
    SOUTH_HIGH_SEAS,
    SOMALIA_BORDER,
    (40.5, 0.0), (41.0, 5.0), (40.0, 11.0), (37.0, 16.0),
]

GULF_OF_GUINEA_OUTLINE = [
    TOGO_COAST,
    GUINEA_HIGH_SEAS,
    CAPE_LOPEZ,
    (10.5, CAPE_LOPEZ[1]), (10.5, 4.5), (9.5, 6.5), (6.0, 7.0), (3.0, 7.2), (1.3, 7.0),
]

AREAS = [
    (
        "Indian Ocean, Gulf of Aden and Southern Red Sea",
        "JWC circular JWLA-032, 18 December 2023. Inside the entry of JWLA-035, 16 September 2026",
        INDIAN_OCEAN_OUTLINE,
    ),
    (
        "Gulf of Guinea",
        "JWC circular JWLA-033, 3 March 2026. Unchanged in JWLA-035, 16 September 2026",
        GULF_OF_GUINEA_OUTLINE,
    ),
]


def main() -> None:
    features = [
        {"type": "Feature", "properties": {"area": name, "source": source}, "geometry": mapping(Polygon(outline))}
        for name, source, outline in AREAS
    ]
    OUTPUT.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
