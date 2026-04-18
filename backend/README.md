# Backend — Builder 2 (Disruptions)

Integrations for real-time disruption signals feeding the risk engine.

| Module        | Source           | Function                  |
|---------------|------------------|---------------------------|
| `fema.py`     | OpenFEMA v2      | `fetch_fema_disasters()`  |
| `noaa.py`     | api.weather.gov  | `fetch_weather_alerts()`  |
| `routes.py`   | derived          | `check_route_status()`    |

## `fema.py` — OpenFEMA Disaster Declarations

Pulls active disaster declarations from the OpenFEMA v2 API, aggregates
per-county rows into one record per disaster, and returns the shape
Builder 3's risk engine expects.

- **Base URL:** `https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries`
- **Auth:** none (no API key required)
- **Docs:** https://www.fema.gov/about/openfema/api

### Install

```bash
pip install -r requirements.txt
```

### Use as a library

```python
from fema import fetch_fema_disasters

disasters = fetch_fema_disasters("IA", days_back=180)
for d in disasters:
    print(d.type, d.counties, d.declaration_date)
```

Each `Disaster` has: `disaster_number, type, state, counties,
declaration_date, incident_begin_date, incident_end_date,
declaration_title, is_active`. Call `.to_dict()` for JSON.

### CLI

```bash
python fema.py IA                      # active IA declarations, last 180d
python fema.py CA --days 365 --json    # raw JSON
python fema.py WY --include-closed     # keep ended incidents too
```

### Tests

```bash
# offline (uses fixtures/fema_sample.json)
python -m pytest test_fema.py -v

# live smoke test against the real FEMA API
LIVE=1 python -m pytest test_fema.py -v -k live
```

### Output contract (handed to Builder 3)

```json
{
  "disaster_number": 4812,
  "type": "Severe Storm",
  "state": "IA",
  "counties": ["Linn (County)", "Polk (County)", "Story (County)"],
  "declaration_date": "2026-03-22T00:00:00.000Z",
  "incident_begin_date": "2026-03-18T00:00:00.000Z",
  "incident_end_date": null,
  "declaration_title": "Severe Storms and Flooding",
  "is_active": true
}
```

---

## `noaa.py` — NWS Active Weather Alerts

Pulls active watches/warnings/advisories filtered to four categories we
care about: **drought, heat, frost, flood**. Tornado warnings, blizzard
warnings, etc. are dropped because they're not in the risk model.

- **Endpoint:** `https://api.weather.gov/alerts/active`
- **Auth:** none — but a descriptive `User-Agent` header is required
  (NWS will reject the request otherwise). Edit `USER_AGENT` in `noaa.py`
  if you want a different contact.
- **Docs:** https://www.weather.gov/documentation/services-web-api

### Use as a library

```python
from noaa import fetch_weather_alerts

# All four categories, entire state of Iowa:
alerts = fetch_weather_alerts("IA")

# Just flood alerts for a specific point (lat,lon):
floods = fetch_weather_alerts("41.59,-93.62", categories=["flood"])

for a in alerts:
    print(a.alert_type, a.severity, a.event, a.expires_at)
```

### CLI

```bash
python noaa.py IA                                  # all four categories
python noaa.py IA --categories flood heat          # subset
python noaa.py "41.59,-93.62" --json               # point lookup, raw JSON
```

### Tests

```bash
python -m pytest test_noaa.py -v                   # offline
LIVE=1 python -m pytest test_noaa.py -v -k live    # live API
```

### Output contract (handed to Builder 3)

```json
{
  "id": "urn:oid:2.49.0.1.840.0.AAA001",
  "alert_type": "flood",
  "event": "Flood Warning",
  "severity": "Severe",
  "affected_area": "Polk, IA; Story, IA; Dallas, IA",
  "areas": ["Polk, IA", "Story, IA", "Dallas, IA"],
  "expires_at": "2026-04-20T12:00:00-05:00",
  "effective_at": "2026-04-18T06:00:00-05:00",
  "headline": "Flood Warning issued April 18 ..."
}
```

---

## `routes.py` — Freight corridor status

Checks whether I-5, I-10, I-80, or I-35 is currently impaired. Status is
derived by intersecting corridor waypoints (defined in `corridors.json`)
with active NOAA alerts and FEMA disasters. No third-party DOT API needed.

- **Status levels:** `clear`, `impaired`, `blocked`
- **Blocks on:** NWS severity `Extreme`, or FEMA Wildfire/Hurricane/Tornado/Earthquake
- **Impairs on:** NWS severity `Severe`/`Moderate`, or any other FEMA disaster type
- **Ignores:** NWS severity `Minor`/`Unknown`

### Corridor definitions

`corridors.json` lists each corridor as an ordered set of (state, county)
waypoints. To extend a corridor, just add more waypoints — no code change.
County names are normalized on comparison so FEMA's `"Polk (County)"` and
NWS's `"Polk, IA"` both match the waypoint `"Polk"`.

### Use as a library

```python
from routes import check_route_status, check_all_corridors

# Pass pre-fetched data (recommended — one fetch, many corridor checks):
from noaa import fetch_weather_alerts
from fema import fetch_fema_disasters

alerts = fetch_weather_alerts("IA") + fetch_weather_alerts("CA")
disasters = fetch_fema_disasters("IA") + fetch_fema_disasters("CA")

i80 = check_route_status("I-80", alerts=alerts, disasters=disasters)
print(i80.status, i80.reason)

# Or let it fetch live for every state in every corridor:
all_statuses = check_all_corridors()
```

### CLI

```bash
python routes.py                    # all four corridors
python routes.py I-80               # single corridor
python routes.py --json             # machine-readable
```

### Tests

```bash
python -m pytest test_routes.py -v
```

### Output contract (handed to Builder 3)

```json
{
  "corridor_id": "I-80",
  "status": "impaired",
  "reason": "Flood Warning (Severe) in 2 segment(s); FEMA Flood disaster #4812 in 3 segment(s)",
  "estimated_duration": "2026-04-20T12:00:00-05:00",
  "crop_types": ["corn", "soybeans", "wheat"],
  "impaired_segments": [
    {"state": "IA", "county": "polk", "source": "NOAA",
     "reason": "Flood Warning", "severity": "Severe",
     "expires_at": "2026-04-20T12:00:00-05:00"}
  ]
}
```
