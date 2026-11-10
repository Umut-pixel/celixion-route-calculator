# sea-route

Sea routes, distances and voyage times as a small HTTP service.

Give it two or more points. It returns the route, the distance in nautical miles, the miles inside an Emission
Control Area and inside a piracy risk area, the canals and straits on the way, the time at sea and the date of every
port call. You can add stops, close passages such as Suez, and add a sea margin.

Built on [searoute-py](https://github.com/genthalili/searoute-py). Distances are for voyage planning, **not for
navigation**.

## Run it

```bash
SEA_ROUTE_TOKEN=dev docker compose up --build
```

The image is built in two stages, runs as a non-root user and reports its health on `/health`. Compose binds the port
to `127.0.0.1` only and refuses to start without `SEA_ROUTE_TOKEN`.

Or without Docker (Python 3.12 or newer):

```bash
pip install -r requirements.txt
uvicorn sea_route.app:app --port 5018
```

To install it as a package instead, `pip install .` (or `pip install -e .` while developing).

## Calculate a route

```bash
curl -X POST localhost:5018/route -H 'Content-Type: application/json' -d '{
  "waypoints": [
    {"name": "Aliaga", "lon": 26.933, "lat": 38.833, "days_in_port": 2},
    {"name": "Alexandria", "lon": 29.833, "lat": 31.166, "days_in_port": 3}
  ],
  "speed_knots": 10,
  "sea_margin_pct": 5,
  "start_time": "2026-11-06T09:00:00Z"
}'
```

| Field | Meaning |
|---|---|
| `waypoints` | 2 to 12 points in sailing order. `days_in_port` is optional. |
| `avoid` | Passages to close: `babalmandab`, `bering`, `bosporus`, `chili`, `gibraltar`, `malacca`, `ormuz`, `panama`, `south_africa`, `suez`, `sunda`. |
| `speed_knots` | Speed for every leg. Default 12. |
| `sea_margin_pct` | Percentage added to time at sea for weather, current and routing. Default 0. |
| `start_time` | Arrival at the first port, with a time zone. Without it, port calls have no dates. |
| `legs` | Optional list with `speed_knots` and `sea_margin_pct` for each leg. |

A route that cannot be sailed with the selected passages closed returns `422`, not zero miles. A point far from
the sea network gets a warning on its leg.

## Find a port

```bash
curl 'localhost:5018/ports?q=rotterdam'
```

## Good to know

- The Northwest Passage is always closed. searoute drops that default as soon as you pass a list, and a closed
  Suez would then route Istanbul to Shanghai through the Arctic.
- Closing Suez alone can send a route through Panama. Close `panama` too if you want the Cape of Good Hope.
- The distance follows the sea network. The drawn line also reaches your two points, which can be far from it:
  the network is coarse near many ports, so a warning means "check this", not "this is wrong".
- Two nearby ports can land on the same network point. The leg then shows the straight line between them with a
  warning, which is a lower bound and can cross land.

## Emission Control Areas

`eca_nm` is the distance inside a sulphur ECA (MARPOL Annex VI, regulation 14): Baltic Sea, North Sea, North
American, United States Caribbean and Mediterranean Sea. It is an estimate for voyage planning.

- The first four come from [Marine Regions](https://www.marineregions.org/downloads.php#eca) (Flanders Marine
  Institute, CC-BY 4.0), simplified to about one nautical mile.
- The Mediterranean is built from MARPOL Annex VI, appendix VII (MEPC.361(79)): the Trafalgar-Spartel line, the
  Canakkale line and the Suez exclusion. The Sea of Marmara and the Black Sea are outside it.
- ECAs adopted after these are not included yet.

`scripts/build_eca.py` rebuilds the data file.

## Piracy risk areas

`piracy_nm` is the distance inside two sea areas of the listed areas published by the
[Joint War Committee](https://lmalloyds.com/committee/joint-war-committee/) (JWC), a joint committee of the Lloyd's
Market Association and the International Underwriting Association.

**The number is indicative.** It is for voyage planning. It is not a measure of threat, an insurance term or security
advice. Zero does not mean a route is safe.

| Area | Limits | Source |
|---|---|---|
| Indian Ocean, Gulf of Aden and Southern Red Sea | The Red Sea south of 18°N. The Yemen border at 16°38.5'N 53°6.5'E, then 14°55'N 53°50'E, 10°48'N 60°15'E and 6°45'S 48°45'E, to the Somalia border at 1°40'S 41°34'E. | [JWLA-032](https://lmalloyds.com/wp-content/uploads/2025/08/JWLA-032-Guyana-1.pdf), 18 December 2023 |
| Gulf of Guinea | The Togo coast at 6°06'45"N 1°12'E, then 0°40'S 3°00'E, to Cape Lopez, Gabon, at 0°40'S 8°42'E. | [JWLA-033](https://lmalloyds.com/wp-content/uploads/2026/03/JWLA-033_Iran.pdf), 3 March 2026, unchanged in [JWLA-035](https://lmalloyds.com/wp-content/uploads/2026/09/JWLA-035-Black-Sea.pdf) |

The JWC lists hull war, piracy, terrorism and related perils together and gives no reason for any one area. Choosing
these two is this project's judgement, not the JWC's.

The first area uses limits older than the current list on purpose. JWLA-032 kept it apart from the Persian Gulf.
JWLA-033, the Iran revision, merged the two and moved the limit out to the Pakistan coast. Counting that whole entry
would call a voyage inside the Persian Gulf a piracy transit. The area here sits inside the current entry, but two of
its limits are no longer lines on the list: 18°N, and the northeast limit from the Yemen border to 10°48'N 60°15'E.

What it does not cover:

- The Persian Gulf, the Gulf of Oman and the Arabian Sea out to 65°E, which the JWC lists since JWLA-033.
- The Red Sea from 18°N to 25.5°N, which the JWC lists since
  [JWLA-034](https://lmalloyds.com/wp-content/uploads/2025/06/JWLA-034-Saudi-Arabia.pdf), 29 July 2026.
- Cabo Delgado, the Black Sea, the Sea of Azov and the countries listed by name, such as Libya or Venezuela.
- Attacks outside the JWC list. The
  [ICC International Maritime Bureau](https://iccwbo.org/news-publications/news/maritime-piracy-incidents-remain-at-historic-lows-despite-somali-piracy-concerns/)
  reported 13 incidents in the Singapore Straits from January to September 2026. Those miles count as zero here.

So a route with `piracy_nm: 0` can still enter waters the JWC lists. This is not a war risk check. Ask your broker.

Good to know:

- **Listed areas change.** The JWC revised the list three times in 2026. These limits were checked against JWLA-035,
  16 September 2026, on 4 November 2026. Check the
  [current circular](https://lmalloyds.com/committee/joint-war-committee/), then update `scripts/build_piracy.py` and
  run it to rebuild the data file.
- **A listing is not an incident count.** The same IMB report has eight hijackings by Somali pirates and two incidents
  in the Gulf of Guinea for those nine months, and both areas stay listed.
- **This is not the Indian Ocean High Risk Area.** Industry withdrew that area on 1 January 2023
  ([MSC 106/INF.10](https://www.intercargo.org/wp-content/uploads/2022/08/MSC-106-INF.10-Removal-of-the-Indian-Ocean-High-Risk-Area-ICS-BIMCO-INTERCARGOOCIMF-INTERTANKO.pdf)).
- **The lines are approximate.** The circulars do not say how to join their points, so they are straight on a
  latitude and longitude grid. The area ends at the coast. JWLA-032 excepted the first 12 nautical miles offshore;
  the lists since JWLA-033 do not, so nothing is cut out here.
- **The sea network is coarse off West Africa.** Ports such as Tema and Lagos sit about 100 nm from it, and the leg
  gets a warning. Miles can be missed near a port inside the area, and a route can wrongly enter it: Abidjan to Tema
  stays west of the area but shows 97 nm, because the network turns off Togo.

## Access

Set `SEA_ROUTE_TOKEN` to require the `X-Sea-Route-Token` header on `/route` and `/ports`. `/health` and the generated
docs (`/docs`, `/redoc`, `/openapi.json`) stay open. `docker compose` refuses to start without the variable. The
service has
no rate limit of its own. Put one in front of it before you expose it.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Warnings fail the run (`filterwarnings = error` in `pyproject.toml`), so a deprecation in a dependency shows up as a
failing test rather than noise. The same suite, plus a Docker build and a call to the running container, runs on every
pull request in GitHub Actions (`.github/workflows/ci.yml`).

## Contributing

Open a branch and a pull request. Keep the open/closed line: this service does routes, distances, zones and voyage
time. Vessels, fuel, cargo and costs belong to the application that calls it, not here. Never commit real mail or
fixture data; the tests use coordinates only.

## License

Apache-2.0. The route network and the port list come from searoute-py, also Apache-2.0. The ECA data derived from
Marine Regions stays under CC-BY 4.0. The piracy areas are this project's drawing of limits from public JWC circulars.
They are not a JWC, LMA or IUA product.
