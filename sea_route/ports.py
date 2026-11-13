"""The port list that ships with searoute-py."""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from importlib.resources import files

# NFKD leaves these letters alone.
BASE_LETTERS = str.maketrans({"ı": "i", "ł": "l", "ø": "o", "đ": "d", "æ": "ae", "œ": "oe"})


@lru_cache(maxsize=1)
def all_ports() -> tuple[dict, ...]:
    data = json.loads(files("searoute.data").joinpath("ports.geojson").read_text(encoding="utf-8"))
    ports = []
    for feature in data["features"]:
        props = feature["properties"]
        lon, lat = feature["geometry"]["coordinates"][:2]
        ports.append({"code": props.get("port"), "name": props.get("name"), "country": props.get("cty"), "lon": lon, "lat": lat})
    return tuple(ports)


def fold(text: str) -> str:
    """Plain letters, so Aliağa and İstanbul find the plain ASCII names in the port list."""
    decomposed = unicodedata.normalize("NFKD", text)
    base = "".join(char for char in decomposed if not unicodedata.combining(char))
    return base.casefold().translate(BASE_LETTERS)


def search_ports(query: str, limit: int = 20) -> list[dict]:
    """Code matches first, then names that start with the query, then names that contain it."""
    needle = fold(query).strip()
    if not needle:
        return []

    def rank(port: dict) -> int | None:
        name = (port["name"] or "").casefold()
        if (port["code"] or "").casefold() == needle:
            return 0
        if name.startswith(needle):
            return 1
        if needle in name:
            return 2
        return None

    ranked = [(score, port) for port in all_ports() if (score := rank(port)) is not None]
    ranked.sort(key=lambda item: (item[0], item[1]["name"] or ""))
    return [port for _, port in ranked[:limit]]
