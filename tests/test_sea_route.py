from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point as ShapelyPoint

from sea_route.app import app
from sea_route.ports import search_ports
from sea_route.routing import Point, RouteError, closed_passages, route_leg
from sea_route.schedule import port_calls, sea_days
from sea_route.zones import eca_area, eca_distance_nm, piracy_area, piracy_distance_nm

ALIAGA = Point(26.933, 38.833)
ALEXANDRIA = Point(29.833, 31.166)
HERAKLION = Point(25.13, 35.34)
ISTANBUL = Point(28.966, 41.016)
SHANGHAI = Point(121.8, 31.2)
ROTTERDAM = Point(4.483, 51.899)
ANKARA = Point(32.86, 39.93)
CONSTANTA = Point(28.66, 44.17)
YOKOHAMA = Point(139.65, 35.44)
LONG_BEACH = Point(-118.2, 33.75)
SUEZ = Point(32.55, 29.9)
MUMBAI = Point(72.8, 18.9)
FUJAIRAH = Point(56.37, 25.17)
RAS_TANURA = Point(50.17, 26.65)
SALALAH = Point(54.0, 16.95)
LAGOS = Point(3.39, 6.42)
DOUALA = Point(9.7, 4.05)

client = TestClient(app)


def test_aliaga_alexandria_is_within_two_percent_of_the_reference():
    assert route_leg(ALIAGA, ALEXANDRIA).distance_nm == pytest.approx(537, rel=0.02)


def test_closing_suez_goes_round_the_cape_not_the_arctic():
    leg = route_leg(ISTANBUL, SHANGHAI, ["suez"])
    assert "south_africa" in leg.passages
    assert "northwest" not in leg.passages
    assert "bering" not in leg.passages
    assert leg.distance_nm > route_leg(ISTANBUL, SHANGHAI).distance_nm


def test_rotterdam_shanghai_needs_panama_closed_too_for_the_cape():
    assert "panama" in route_leg(ROTTERDAM, SHANGHAI, ["suez"]).passages
    assert "south_africa" in route_leg(ROTTERDAM, SHANGHAI, ["suez", "panama"]).passages


def test_northwest_stays_closed_on_every_request():
    assert closed_passages([]) == ["northwest"]
    assert closed_passages(["suez"]) == ["northwest", "suez"]


def test_unknown_passage_is_refused():
    with pytest.raises(RouteError):
        closed_passages(["suzz"])


def test_blocked_route_is_an_error_not_zero_miles():
    with pytest.raises(RouteError):
        route_leg(ALIAGA, CONSTANTA, ["bosporus"])


def test_a_port_at_the_mouth_of_a_strait_can_sail_away_from_it():
    leg = route_leg(ISTANBUL, ALIAGA, ["bosporus"])
    assert leg.distance_nm == pytest.approx(241.3, abs=1)
    assert "bosporus" not in leg.passages
    with pytest.raises(RouteError):
        route_leg(ISTANBUL, CONSTANTA, ["bosporus"])


def test_a_real_transit_keeps_its_passage():
    assert "suez" in route_leg(ROTTERDAM, SHANGHAI).passages
    assert "panama" in route_leg(Point(-95.0, 29.3), Point(-77.2, -12.0)).passages


@pytest.mark.parametrize(
    "origin, destination, eca, piracy",
    [
        (YOKOHAMA, LONG_BEACH, 701.8, 0),
        (Point(129.04, 35.1), Point(-123.1, 49.3), 572.5, 0),
        (Point(39.67, -4.06), LONG_BEACH, 471.9, 628.1),
    ],
)
def test_zone_miles_match_both_ways_across_the_antimeridian(origin, destination, eca, piracy):
    there, back = route_leg(origin, destination), route_leg(destination, origin)
    assert (there.eca_nm, there.piracy_nm) == pytest.approx((back.eca_nm, back.piracy_nm), abs=0.5)
    assert there.eca_nm == pytest.approx(eca, abs=2)
    assert there.piracy_nm == pytest.approx(piracy, abs=2)


@pytest.mark.parametrize("origin, destination", [(YOKOHAMA, LONG_BEACH), (LONG_BEACH, Point(39.67, -4.06))])
def test_drawn_line_never_jumps_round_the_world(origin, destination):
    line = route_leg(origin, destination).coordinates
    assert max(abs(b[0] - a[0]) for a, b in zip(line, line[1:])) < 180


def test_ports_on_one_network_point_get_a_straight_line_and_a_warning():
    leg = route_leg(Point(13.58, 41.21), Point(14.27, 40.84))  # Gaeta, Napoli
    assert leg.distance_nm > 0
    assert any("straight line" in warning for warning in leg.warnings)


def test_zone_distance_is_safe_across_threads():
    line = route_leg(ROTTERDAM, SHANGHAI).coordinates[1:-1]
    expected = eca_distance_nm(line)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: eca_distance_nm(line), range(64)))
    assert set(results) == {expected}


@pytest.mark.parametrize(
    "query, code",
    [("İstanbul", "TRIST"), ("Aliağa", "TRALI"), ("Bandırma", "TRBDM"), ("Gdańsk", "PLGDN")],
)
def test_port_search_understands_accents(query, code):
    assert code in [port["code"] for port in search_ports(query)]


def test_port_search_ignores_marks_alone():
    assert search_ports("\u0301\u0301") == []


def test_same_point_is_a_zero_mile_leg_not_a_blocked_route():
    leg = route_leg(ALIAGA, ALIAGA)
    assert leg.distance_nm == 0
    assert leg.passages == ()


def test_line_reaches_both_points():
    leg = route_leg(ALIAGA, ALEXANDRIA)
    assert leg.coordinates[0] == (ALIAGA.lon, ALIAGA.lat)
    assert leg.coordinates[-1] == (ALEXANDRIA.lon, ALEXANDRIA.lat)


def test_inland_point_is_flagged():
    assert route_leg(ANKARA, ALEXANDRIA).warnings
    assert not route_leg(ALIAGA, ALEXANDRIA).warnings


@pytest.mark.parametrize(
    "lon, lat, inside",
    [
        (26.8, 38.7, True),  # Aegean, off Aliaga
        (29.8, 31.5, True),  # off Alexandria
        (14.5, 35.8, True),  # off Malta
        (13.5, 45.4, True),  # Gulf of Trieste
        (26.5, 40.5, True),  # Gulf of Saros
        (-5.6, 35.95, True),  # Strait of Gibraltar, inside the Trafalgar-Spartel line
        (-6.5, 36.0, False),  # Atlantic, outside that line
        (26.3, 40.1, False),  # Dardanelles, past the Canakkale line
        (28.0, 40.7, False),  # Sea of Marmara
        (30.0, 43.0, False),  # Black Sea
        (32.4, 31.35, False),  # Port Said exclusion
        (32.55, 29.8, False),  # Gulf of Suez
        (3.0, 54.0, True),  # North Sea
        (20.0, 58.0, True),  # Baltic
        (-72.0, 39.0, True),  # North American area
        (-30.0, 40.0, False),  # mid Atlantic
    ],
)
def test_eca_boundaries(lon, lat, inside):
    assert eca_area().contains(ShapelyPoint(lon, lat)) is inside


def test_aliaga_alexandria_runs_inside_the_mediterranean_eca():
    leg = route_leg(ALIAGA, ALEXANDRIA)
    assert leg.eca_nm == pytest.approx(leg.distance_nm, rel=0.02)
    assert leg.eca_nm <= leg.distance_nm


def test_eca_miles_stop_at_the_dardanelles():
    leg = route_leg(ISTANBUL, ALIAGA)
    assert 0 < leg.eca_nm < leg.distance_nm


def test_route_with_no_eca_reports_zero():
    assert route_leg(Point(55.0, -21.0), Point(72.8, 18.9)).eca_nm == 0


def test_antimeridian_route_does_not_count_the_long_way_round():
    assert eca_distance_nm([(179.0, 0.0), (-179.0, 0.0)]) == 0


@pytest.mark.parametrize(
    "lon, lat, inside",
    [
        (48.0, 13.0, True),  # Gulf of Aden
        (43.3, 12.6, True),  # Bab el-Mandeb
        (40.5, 16.5, True),  # Southern Red Sea
        (54.5, 12.0, True),  # off Socotra
        (52.0, 0.0, True),  # Somali Basin, inside the line to 6 45S 48 45E
        (47.0, -4.0, True),  # north of the Somalia border line
        (38.9, 19.5, False),  # Red Sea north of 18N, added by JWLA-034
        (55.0, 0.0, False),  # east of the line to 6 45S 48 45E
        (47.0, -6.0, False),  # south of the Somalia border line
        (54.5, 16.5, False),  # off Salalah, past the northeast limit
        (62.0, 15.0, False),  # Arabian Sea, added by JWLA-033
        (58.5, 24.5, False),  # Gulf of Oman
        (51.5, 27.0, False),  # Persian Gulf
        (3.4, 5.5, True),  # off Lagos
        (7.0, 3.5, True),  # off Bonny
        (1.5, 5.9, True),  # off Lome
        (6.7, 0.2, True),  # off Sao Tome
        (8.0, -0.3, True),  # north of the Cape Lopez line
        (0.5, 5.0, False),  # off Ghana, west of the Togo line
        (1.8, 3.0, False),  # just west of the line to 0 40S 3E
        (6.0, -1.5, False),  # south of the Cape Lopez line
        (-4.0, 4.5, False),  # off Abidjan
        (11.5, -5.0, False),  # off Pointe-Noire
        (40.6, -11.5, False),  # Cabo Delgado, left out
        (30.0, 43.0, False),  # Black Sea, left out
        (103.8, 1.2, False),  # Singapore Strait, not on the JWC list
    ],
)
def test_piracy_boundaries(lon, lat, inside):
    assert piracy_area().contains(ShapelyPoint(lon, lat)) is inside


def test_route_through_the_gulf_of_aden_counts_piracy_miles():
    leg = route_leg(SUEZ, MUMBAI)
    assert "babalmandab" in leg.passages
    assert 1000 < leg.piracy_nm < 1130  # 18N to Bab el-Mandeb, then along the Gulf of Aden to the eastern limit
    assert leg.piracy_nm < leg.distance_nm


def test_route_along_the_gulf_of_guinea_counts_piracy_miles():
    leg = route_leg(LAGOS, DOUALA)
    assert leg.piracy_nm == pytest.approx(leg.distance_nm, rel=0.02)
    assert leg.piracy_nm <= leg.distance_nm


def test_mediterranean_route_has_no_piracy_miles():
    assert route_leg(ALIAGA, ALEXANDRIA).piracy_nm == 0


@pytest.mark.parametrize(
    "origin, destination",
    [(FUJAIRAH, RAS_TANURA), (MUMBAI, FUJAIRAH), (SALALAH, FUJAIRAH)],
)
def test_the_waters_added_for_iran_are_not_counted_as_piracy(origin, destination):
    assert route_leg(origin, destination).piracy_nm == 0


def test_going_round_the_cape_leaves_the_piracy_areas():
    through_suez = route_leg(ROTTERDAM, SHANGHAI)
    round_the_cape = route_leg(ROTTERDAM, SHANGHAI, ["suez", "panama"])
    assert through_suez.piracy_nm > 1000
    assert round_the_cape.piracy_nm == 0


def test_a_single_point_has_no_piracy_miles():
    assert piracy_distance_nm([(48.0, 13.0)]) == 0


def test_sea_days_with_margin():
    assert sea_days(240, 10) == 1
    assert sea_days(240, 10, 10) == pytest.approx(1.1)


@pytest.mark.parametrize("speed, margin", [(0, 0), (-1, 0), (10, -1)])
def test_sea_days_refuses_bad_input(speed, margin):
    with pytest.raises(ValueError):
        sea_days(100, speed, margin)


def test_port_calls_follow_the_reference_voyage():
    start = datetime(2026, 10, 21, 13, 5, tzinfo=timezone.utc)
    origin, destination = port_calls(start, [2, 3], [sea_days(537, 10)])
    assert origin.departure == start + timedelta(days=2)
    assert destination.arrival == start + timedelta(days=2, hours=53.7)
    assert destination.departure == destination.arrival + timedelta(days=3)


def test_port_calls_without_a_start_time():
    assert port_calls(None, [1, 1], [1])[0].arrival is None


def test_port_search_ranks_exact_code_first():
    assert search_ports("NLRTM")[0]["code"] == "NLRTM"
    assert search_ports("") == []


def test_route_endpoint_sums_via_legs():
    body = {
        "waypoints": [
            {"lon": ALIAGA.lon, "lat": ALIAGA.lat, "name": "Aliaga", "days_in_port": 2},
            {"lon": HERAKLION.lon, "lat": HERAKLION.lat, "name": "Heraklion"},
            {"lon": ALEXANDRIA.lon, "lat": ALEXANDRIA.lat, "name": "Alexandria", "days_in_port": 3},
        ],
        "speed_knots": 10,
        "start_time": "2026-10-21T13:05:00Z",
    }
    response = client.post("/route", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["distance_nm"] == pytest.approx(sum(leg["distance_nm"] for leg in data["legs"]), abs=0.11)
    assert len(data["port_calls"]) == 3
    assert 0 < data["eca_nm"] <= data["distance_nm"]
    assert data["port_days"] == 5


def test_route_endpoint_reports_piracy_miles_per_leg_and_in_total():
    body = {
        "waypoints": [
            {"lon": ALIAGA.lon, "lat": ALIAGA.lat},
            {"lon": SUEZ.lon, "lat": SUEZ.lat},
            {"lon": MUMBAI.lon, "lat": MUMBAI.lat},
        ],
    }
    data = client.post("/route", json=body).json()
    first, second = data["legs"]
    assert first["piracy_nm"] == 0
    assert second["piracy_nm"] > 0
    assert data["piracy_nm"] == second["piracy_nm"]


def test_route_endpoint_reports_a_blocked_route():
    body = {
        "waypoints": [{"lon": ISTANBUL.lon, "lat": ISTANBUL.lat}, {"lon": SHANGHAI.lon, "lat": SHANGHAI.lat}],
        "avoid": ["panama", "suez", "south_africa", "chili"],
    }
    assert client.post("/route", json=body).status_code == 422


def test_start_time_needs_a_zone():
    body = {
        "waypoints": [{"lon": ALIAGA.lon, "lat": ALIAGA.lat}, {"lon": ALEXANDRIA.lon, "lat": ALEXANDRIA.lat}],
        "start_time": "2026-10-21T13:05:00",
    }
    assert client.post("/route", json=body).status_code == 422


def test_non_ascii_token_is_refused_not_a_crash(monkeypatch):
    monkeypatch.setenv("SEA_ROUTE_TOKEN", "test-token")
    assert client.get("/ports", params={"q": "rotter"}, headers={"X-Sea-Route-Token": b"\xe9"}).status_code == 401


def test_slow_speed_and_far_dates_are_refused_not_a_crash():
    points = [{"lon": ALIAGA.lon, "lat": ALIAGA.lat}, {"lon": ALEXANDRIA.lon, "lat": ALEXANDRIA.lat}]
    assert client.post("/route", json={"waypoints": points, "speed_knots": 0.0001}).status_code == 422
    body = {"waypoints": [{**points[0], "days_in_port": 300}, points[1]], "start_time": "9999-12-31T23:00:00Z"}
    assert client.post("/route", json=body).status_code == 422


def test_nan_in_a_body_is_refused_not_a_crash():
    payload = '{"waypoints":[{"lon":NaN,"lat":1},{"lon":2,"lat":3}]}'
    response = client.post("/route", content=payload, headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def test_token_is_enforced_when_configured(monkeypatch):
    monkeypatch.setenv("SEA_ROUTE_TOKEN", "test-token")
    assert client.get("/ports", params={"q": "rotter"}).status_code == 401
    assert client.get("/ports", params={"q": "rotter"}, headers={"X-Sea-Route-Token": "test-token"}).status_code == 200
    assert client.get("/health").status_code == 200
