"""HTTP API. Set SEA_ROUTE_TOKEN to require the X-Sea-Route-Token header on /route and /ports. /health and the
generated docs stay open."""
from __future__ import annotations

import hmac
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from . import __version__
from .ports import search_ports
from .routing import AVOIDABLE_PASSAGES, Point, RouteError, prepare_network, route_leg
from .schedule import port_calls, sea_days
from .zones import eca_area, piracy_area

MAX_WAYPOINTS = 12


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # A few seconds of loading, so it happens here and not on the first request.
    prepare_network()
    eca_area()
    piracy_area()
    yield


app = FastAPI(title="sea-route", version=__version__, lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:
    """Leaves out the rejected input: NaN and lone surrogates cannot be written back as JSON."""
    fields = ("type", "loc", "msg")
    return JSONResponse(status_code=422, content={"detail": [{key: item.get(key) for key in fields} for item in error.errors()]})


def require_token(x_sea_route_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("SEA_ROUTE_TOKEN", "")
    # Starlette decodes headers as latin-1, so this gets back the bytes that were sent.
    if expected and not hmac.compare_digest((x_sea_route_token or "").encode("latin-1"), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid token")


class Waypoint(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    name: str | None = Field(default=None, max_length=120)
    days_in_port: float = Field(default=0, ge=0, le=365)


class LegOptions(BaseModel):
    speed_knots: float | None = Field(default=None, ge=1, le=40)
    sea_margin_pct: float | None = Field(default=None, ge=0, le=100)


class RouteRequest(BaseModel):
    waypoints: list[Waypoint] = Field(min_length=2, max_length=MAX_WAYPOINTS)
    avoid: list[str] = Field(default_factory=list, max_length=len(AVOIDABLE_PASSAGES))
    speed_knots: float = Field(default=12, ge=1, le=40)
    sea_margin_pct: float = Field(default=0, ge=0, le=100)
    start_time: datetime | None = None
    legs: list[LegOptions] | None = None

    @field_validator("start_time")
    @classmethod
    def start_time_has_zone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("start_time needs a time zone, for example 2026-11-06T09:00:00Z")
        return value

    @model_validator(mode="after")
    def one_option_per_leg(self) -> RouteRequest:
        if self.legs is not None and len(self.legs) != len(self.waypoints) - 1:
            raise ValueError("legs needs one entry per leg")
        return self


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/ports", dependencies=[Depends(require_token)])
def ports(q: str = Query(min_length=2, max_length=60), limit: int = Query(default=20, ge=1, le=50)) -> dict:
    return {"items": search_ports(q, limit)}


@app.post("/route", dependencies=[Depends(require_token)])
def route(request: RouteRequest) -> dict:
    points = [Point(w.lon, w.lat) for w in request.waypoints]
    options = request.legs or [LegOptions() for _ in points[1:]]

    legs = []
    try:
        for origin, destination, option in zip(points, points[1:], options):
            leg = route_leg(origin, destination, request.avoid)
            speed = option.speed_knots if option.speed_knots is not None else request.speed_knots
            margin = option.sea_margin_pct if option.sea_margin_pct is not None else request.sea_margin_pct
            legs.append((leg, speed, margin, sea_days(leg.distance_nm, speed, margin)))
    except RouteError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    days_in_port = [w.days_in_port for w in request.waypoints]
    leg_days = [days for *_, days in legs]
    try:
        calls = port_calls(request.start_time, days_in_port, leg_days)
    except OverflowError as error:
        raise HTTPException(status_code=422, detail="The voyage runs past the last supported date") from error

    return {
        "distance_nm": round(sum(leg.distance_nm for leg, *_ in legs), 1),
        "eca_nm": round(sum(leg.eca_nm for leg, *_ in legs), 1),
        "piracy_nm": round(sum(leg.piracy_nm for leg, *_ in legs), 1),
        "sea_days": round(sum(leg_days), 4),
        "port_days": sum(days_in_port),
        "duration_days": round(sum(leg_days) + sum(days_in_port), 4),
        "legs": [
            {
                "distance_nm": leg.distance_nm,
                "eca_nm": leg.eca_nm,
                "piracy_nm": leg.piracy_nm,
                "speed_knots": speed,
                "sea_margin_pct": margin,
                "sea_days": round(days, 4),
                "passages": leg.passages,
                "warnings": leg.warnings,
                "coordinates": leg.coordinates,
            }
            for leg, speed, margin, days in legs
        ],
        "port_calls": [
            {
                "name": waypoint.name,
                "days_in_port": waypoint.days_in_port,
                "arrival": call.arrival,
                "departure": call.departure,
            }
            for waypoint, call in zip(request.waypoints, calls)
        ],
    }
