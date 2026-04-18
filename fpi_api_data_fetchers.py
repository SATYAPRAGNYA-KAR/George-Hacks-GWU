"""
FPI Data Fetchers — CropSmart Community Dashboard
Builder 3 · Data Layer

All public functions return a standardized envelope:
{
    "source": str,
    "status": "ok" | "partial" | "error",
    "data":   dict | list,
    "error":  str | None
}

APIs covered:
  1. Open-Meteo          — live weather + soil moisture          (NO KEY)
  2. NOAA Weather Alerts — active watches/warnings               (NO KEY)
  3. OpenFEMA            — active disaster declarations           (NO KEY)
  4. USDA NASS QuickStats— crop production + prices              (KEY: NASS_API_KEY)
  5. USDA VegScape WMS   — live NDVI by lat/lon                  (NO KEY)
  6. Census ACS          — poverty rate + SNAP participation      (KEY: CENSUS_API_KEY)
  7. USDA Local Food     — farmers markets + food hubs by state   (KEY: USDA_FOOD_KEY)
  8. NOAA CDO            — precipitation anomaly by station       (KEY: NOAA_CDO_KEY)

Set keys as environment variables:
  export NASS_API_KEY="..."
  export CENSUS_API_KEY="..."
  export USDA_FOOD_KEY="..."
  export NOAA_CDO_KEY="..."
"""

import os
import re
import time
import requests
from datetime import datetime, timedelta
from typing import Optional

# ── Louisiana bounding box (EPSG:4326) ────────────────────────────────────────
LA_BBOX = {
    "lat_min": 28.9, "lat_max": 33.0,
    "lon_min": -94.1, "lon_max": -88.8,
}

# ── keys from env ─────────────────────────────────────────────────────────────
NASS_API_KEY   = os.getenv("NASS_API_KEY", "4C993D49-0BF4-3A30-B8CC-4E55C117CA5C")
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", "6efd6fdbf62770505ddff277f346aec714cf2f48")
USDA_FOOD_KEY  = os.getenv("USDA_FOOD_KEY", "")
NOAA_CDO_KEY   = os.getenv("NOAA_CDO_KEY", "NhOHySJRWxffJJVhIhsKfzaonSKhnAZc")

# ── shared helpers ────────────────────────────────────────────────────────────

def _get(url: str, params: dict = None, headers: dict = None,
         timeout: int = 20, retries: int = 3) -> Optional[requests.Response]:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            elif r.status_code in (429, 503):
                wait = 2 ** attempt
                print(f"  [WARN] {url} -> {r.status_code}, retrying in {wait}s")
                time.sleep(wait)
            else:
                print(f"  [WARN] {url} -> {r.status_code}")
                return None
        except requests.Timeout:
            print(f"  [WARN] timeout on attempt {attempt + 1}: {url}")
            time.sleep(1)
        except requests.ConnectionError as e:
            print(f"  [WARN] connection error attempt {attempt + 1}: {e}")
            time.sleep(1)
    print(f"  [ERR] all {retries} attempts failed: {url}")
    return None

def _ok(source: str, data) -> dict:
    return {"source": source, "status": "ok", "data": data, "error": None}

def _partial(source: str, data, msg: str) -> dict:
    return {"source": source, "status": "partial", "data": data, "error": msg}

def _err(source: str, msg: str) -> dict:
    return {"source": source, "status": "error", "data": {}, "error": msg}


# =============================================================================
# 1. OPEN-METEO — live weather + soil moisture (NO KEY)
# =============================================================================

def fetch_open_meteo(lat: float, lon: float) -> dict:
    """
    Live hourly weather for a lat/lon point.
    Returns temperature, precipitation, soil moisture (0-7cm), wind speed.
    Latency: real-time (sub-hour lag).
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude":      lat,
        "longitude":     lon,
        "hourly":        "temperature_2m,precipitation,soil_moisture_0_1cm,wind_speed_10m",
        "current":       "temperature_2m,precipitation,wind_speed_10m",
        "forecast_days": 3,
        "timezone":      "America/Chicago",
    }

    r = _get(url, params=params, timeout=15)
    if r is None:
        return _err("open_meteo", "Request failed after retries")

    try:
        j       = r.json()
        current = j.get("current", {})
        hourly  = j.get("hourly", {})

        # Soil moisture: Open-Meteo returns a 72-hour series mixing past
        # observations and future forecasts. Both are valid — just take
        # the first non-None value anywhere in the series.
        sm_series = hourly.get("soil_moisture_0_1cm", [])
        latest_sm = next((v for v in sm_series if v is not None), None)

        precip_series = hourly.get("precipitation", [])
        precip_24h    = sum(v for v in precip_series[:24] if v is not None)

        return _ok("open_meteo", {
            "lat":                lat,
            "lon":                lon,
            "current_temp_c":     current.get("temperature_2m"),
            "current_precip_mm":  current.get("precipitation"),
            "current_wind_kmh":   current.get("wind_speed_10m"),
            "soil_moisture_m3m3": latest_sm,
            "precip_24h_mm":      round(precip_24h, 2),
            "fetched_at":         datetime.utcnow().isoformat() + "Z",
        })
    except Exception as e:
        return _err("open_meteo", f"Parse error: {e}")


# =============================================================================
# 2. NOAA WEATHER ALERTS — active watches/warnings (NO KEY)
# =============================================================================

def fetch_noaa_alerts(state: str = "LA") -> dict:
    """
    Active NWS weather alerts for a US state (2-letter code).
    Covers: flood, drought, extreme heat, tornado, hurricane watches.
    Latency: real-time (minutes).
    """
    url     = "https://api.weather.gov/alerts/active"
    params  = {"area": state}
    headers = {"User-Agent": "CropSmart-FPI/1.0 (cropsmart@george.edu)"}

    r = _get(url, params=params, headers=headers, timeout=20)
    if r is None:
        return _err("noaa_alerts", "Request failed")

    try:
        features = r.json().get("features", [])
        alerts   = []
        for f in features:
            props = f.get("properties", {})
            alerts.append({
                "event":       props.get("event"),
                "severity":    props.get("severity"),
                "certainty":   props.get("certainty"),
                "urgency":     props.get("urgency"),
                "headline":    props.get("headline"),
                "area":        props.get("areaDesc"),
                "onset":       props.get("onset"),
                "expires":     props.get("expires"),
                "description": props.get("description", "")[:300],
            })

        severity_map  = {"Extreme": 1.0, "Severe": 0.75, "Moderate": 0.5, "Minor": 0.25}
        max_severity  = max(
            (severity_map.get(a["severity"], 0) for a in alerts), default=0.0
        )

        return _ok("noaa_alerts", {
            "state":              state,
            "active_count":       len(alerts),
            "max_severity_score": max_severity,
            "alerts":             alerts,
            "fetched_at":         datetime.utcnow().isoformat() + "Z",
        })
    except Exception as e:
        return _err("noaa_alerts", f"Parse error: {e}")


# =============================================================================
# 3. OPENFEMA — active disaster declarations (NO KEY)
# =============================================================================

def fetch_fema_disasters(state: str = "LA", days_back: int = 180) -> dict:
    """
    Active or recent FEMA disaster declarations for a state.
    Latency: updated daily.
    """
    # FIX: PascalCase dataset name (case-sensitive) + User-Agent header
    url    = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
    cutoff = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    params = {
        "$filter":      f"state eq '{state}' and declarationDate gt '{cutoff}'",
        "$orderby":     "declarationDate desc",
        "$top":         50,
        "$inlinecount": "allpages",
    }
    headers = {
        "Accept":     "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; CropSmart-FPI/1.0)",
    }

    r = _get(url, params=params, headers=headers, timeout=25)

    # Fallback: try v1 endpoint
    if r is None:
        r = _get(
            "https://www.fema.gov/api/open/v1/DisasterDeclarationsSummaries",
            params=params, headers=headers, timeout=25
        )

    # Last resort: NOAA Drought Monitor
    if r is None:
        print("  [INFO] FEMA unreachable — falling back to NOAA Drought Monitor")
        return _fetch_drought_monitor_fallback(state)

    try:
        body     = r.json()
        records  = (body.get("DisasterDeclarationsSummaries")
                    or body.get("disasterDeclarationsSummaries")
                    or [])

        disasters = []
        for rec in records:
            disasters.append({
                "disaster_number":  rec.get("disasterNumber"),
                "declaration_type": rec.get("declarationType"),
                "incident_type":    rec.get("incidentType"),
                "title":            rec.get("declarationTitle"),
                "declaration_date": rec.get("declarationDate"),
                "incident_begin":   rec.get("incidentBeginDate"),
                "incident_end":     rec.get("incidentEndDate"),
                "county":           rec.get("designatedArea"),
                "fips":             str(rec.get("fipsStateCode", "")) + str(rec.get("fipsCountyCode", "")),
            })

        active = [d for d in disasters if not d["incident_end"]]

        return _ok("openfema", {
            "state":            state,
            "total_recent":     len(disasters),
            "active_count":     len(active),
            "active_disasters": active,
            "all_disasters":    disasters,
            "fetched_at":       datetime.utcnow().isoformat() + "Z",
        })
    except Exception as e:
        return _err("openfema", f"Parse error: {e}")


def _fetch_drought_monitor_fallback(state: str = "LA") -> dict:
    """NOAA/UNL Drought Monitor — fallback when FEMA is unreachable."""
    url    = "https://usdm.climate.gov/api/usdm/v1/state"
    params = {"StateAbbreviation": state}

    r = _get(url, params=params, timeout=15)
    if r is None:
        return _partial("openfema_drought_fallback", {
            "state":          state,
            "active_count":   0,
            "fetched_at":     datetime.utcnow().isoformat() + "Z",
        }, "All FEMA/drought endpoints unreachable")

    try:
        data = r.json()
        return _ok("openfema_drought_fallback", {
            "state":        state,
            "active_count": 1 if data else 0,
            "drought_data": data,
            "fetched_at":   datetime.utcnow().isoformat() + "Z",
        })
    except Exception as e:
        return _err("openfema_drought_fallback", f"Parse error: {e}")


# =============================================================================
# 4. USDA NASS QUICKSTATS — crop production + prices (KEY REQUIRED)
# =============================================================================

def fetch_nass_quickstats(state_alpha: str = "LA",
                           commodity: str = "SUGARCANE FOR SUGAR",
                           year: int = None) -> dict:
    """
    USDA NASS QuickStats — official crop production estimates.
    Latency: weekly to monthly during growing season.
    Get your free key at: https://quickstats.nass.usda.gov/api
    Louisiana commodities: SUGARCANE FOR SUGAR, RICE, SOYBEANS, COTTON
    """
    if not NASS_API_KEY:
        return _err("nass_quickstats", "NASS_API_KEY not set in environment")

    year   = year or datetime.utcnow().year - 1
    url    = "https://quickstats.nass.usda.gov/api/api_GET/"
    params = {
        "key":            NASS_API_KEY,
        "source_desc":    "SURVEY",
        "sector_desc":    "CROPS",
        "commodity_desc": commodity.upper(),
        "state_alpha":    state_alpha,
        "year":           year,
        "agg_level_desc": "STATE",
        "format":         "JSON",
    }

    r = _get(url, params=params, timeout=30)
    if r is None:
        return _err("nass_quickstats", "Request failed")

    try:
        data = r.json().get("data", [])
        if not data:
            # QuickStats lags ~6 months — try previous year
            params["year"] = year - 1
            r2   = _get(url, params=params, timeout=30)
            data = r2.json().get("data", []) if r2 else []

        records = []
        for row in data:
            val_str = row.get("Value", "").replace(",", "").strip()
            try:
                value = float(val_str)
            except ValueError:
                value = None  # suppressed values "(D)" or "(Z)"

            records.append({
                "county":    row.get("county_name"),
                "commodity": row.get("commodity_desc"),
                "stat_cat":  row.get("statisticcat_desc"),
                "unit":      row.get("unit_desc"),
                "value":     value,
                "year":      row.get("year"),
            })

        return _ok("nass_quickstats", {
            "state":      state_alpha,
            "commodity":  commodity,
            "year":       year,
            "records":    records,
            "fetched_at": datetime.utcnow().isoformat() + "Z",
        })
    except Exception as e:
        return _err("nass_quickstats", f"Parse error: {e}")


# =============================================================================
# 5. USDA VEGSCAPE — live NDVI (NO KEY)
# =============================================================================

def fetch_vegscape_ndvi(lat: float, lon: float,
                         product: str = "NDVI") -> dict:
    """
    Live NDVI at a lat/lon point via VegScape WMS GetFeatureInfo.
    Falls back to NASA CMR STAC, then Open-Meteo ET proxy.
    Latency: weekly updates during growing season.
    """

    # Attempt 1: VegScape WMS GetFeatureInfo
    wms_url  = "https://nassgeodata.gmu.edu/VegScapeService/wms_vegscape.cgi"
    delta    = 0.01
    bbox_str = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"

    params = {
        "SERVICE":      "WMS",
        "VERSION":      "1.1.1",
        "REQUEST":      "GetFeatureInfo",
        "LAYERS":       "NDVI_WEEKLY",
        "QUERY_LAYERS": "NDVI_WEEKLY",
        "STYLES":       "",
        "SRS":          "EPSG:4326",
        "BBOX":         bbox_str,
        "WIDTH":        100,
        "HEIGHT":       100,
        "X":            50,
        "Y":            50,
        "INFO_FORMAT":  "text/plain",
    }

    r = _get(wms_url, params=params, timeout=25)
    if r is not None and r.status_code == 200:
        match = re.search(r'(?:value|ndvi)\s*[=:]\s*([\d.]+)', r.text, re.IGNORECASE)
        if match:
            raw  = float(match.group(1))
            ndvi = raw / 255.0 if raw > 1 else raw  # byte-scale same as NAFSI
            return _ok("vegscape_ndvi", {
                "lat":             lat,
                "lon":             lon,
                "product":         product,
                "ndvi":            round(ndvi, 4),
                "source_endpoint": "VegScape WMS",
                "fetched_at":      datetime.utcnow().isoformat() + "Z",
            })

    # Attempt 2: NASA CMR STAC — MODIS MOD13Q1 (no key)
    print("  [INFO] VegScape WMS failed — trying NASA CMR STAC")
    cmr_url    = "https://cmr.earthdata.nasa.gov/stac/LPDAAC_ECS/search"
    cmr_params = {
        "collections": "MOD13Q1.v061",
        "bbox":        f"{lon-0.1},{lat-0.1},{lon+0.1},{lat+0.1}",
        "limit":       1,
        "sortby":      "-datetime",
    }

    r2 = _get(cmr_url, params=cmr_params, timeout=20)
    if r2 is not None:
        try:
            items = r2.json().get("features", [])
            if items:
                granule_date = items[0].get("properties", {}).get("datetime", "")[:10]
                return _partial("vegscape_ndvi", {
                    "lat":                lat,
                    "lon":                lon,
                    "product":            "MOD13Q1 NDVI",
                    "ndvi":               None,
                    "latest_granule_date": granule_date,
                    "note":               "CMR confirms coverage; pixel value needs AppEEARS token",
                    "source_endpoint":    "NASA CMR STAC",
                    "fetched_at":         datetime.utcnow().isoformat() + "Z",
                }, "NDVI pixel value unavailable without AppEEARS auth")
        except Exception:
            pass

    # Attempt 3: Open-Meteo ET as vegetation stress proxy
    print("  [INFO] CMR failed — using Open-Meteo ET as NDVI proxy")
    et_params = {
        "latitude":      lat,
        "longitude":     lon,
        "daily":         "et0_fao_evapotranspiration",
        "forecast_days": 1,
        "timezone":      "America/Chicago",
    }
    r3 = _get("https://api.open-meteo.com/v1/forecast", params=et_params, timeout=15)
    if r3 is not None:
        try:
            et_vals = r3.json().get("daily", {}).get("et0_fao_evapotranspiration", [None])
            return _partial("vegscape_ndvi", {
                "lat":             lat,
                "lon":             lon,
                "product":         "ET_proxy",
                "ndvi":            None,
                "et0_mm_day":      et_vals[0] if et_vals else None,
                "note":            "ET proxy for vegetation stress — not true NDVI",
                "source_endpoint": "Open-Meteo ET",
                "fetched_at":      datetime.utcnow().isoformat() + "Z",
            }, "Using ET proxy — VegScape and CMR both unreachable")
        except Exception:
            pass

    return _err("vegscape_ndvi", "All NDVI endpoints failed")


# =============================================================================
# 6. CENSUS ACS — poverty rate + SNAP participation (KEY REQUIRED)
# =============================================================================

def fetch_census_vulnerability(state_fips: str = "22") -> dict:
    """
    Census ACS 5-year estimates — county-level poverty + SNAP rates.
    Louisiana FIPS = "22".
    Latency: annual (static baseline — does not change daily).
    Get your free key at: https://api.census.gov/data/key_signup.html
    """
    if not CENSUS_API_KEY:
        return _err("census_acs", "CENSUS_API_KEY not set in environment")

    url    = "https://api.census.gov/data/2022/acs/acs5"
    params = {
        "get": "NAME,B17001_001E,B17001_002E,B22010_001E,B22010_002E",
        "for": "county:*",
        "in":  f"state:{state_fips}",
        "key": CENSUS_API_KEY,
    }

    r = _get(url, params=params, timeout=25)
    if r is None:
        return _err("census_acs", "Request failed")

    try:
        rows   = r.json()
        header = rows[0]

        counties = []
        for row in rows[1:]:
            d          = dict(zip(header, row))
            total_pop  = int(d.get("B17001_001E") or 0)
            poverty_pop = int(d.get("B17001_002E") or 0)
            total_hh   = int(d.get("B22010_001E") or 0)
            snap_hh    = int(d.get("B22010_002E") or 0)

            poverty_rate  = poverty_pop / total_pop if total_pop > 0 else 0
            snap_rate     = snap_hh    / total_hh   if total_hh  > 0 else 0
            vulnerability = round(0.6 * poverty_rate + 0.4 * snap_rate, 4)

            counties.append({
                "county_name":         d.get("NAME"),
                "state_fips":          d.get("state"),
                "county_fips":         d.get("state") + d.get("county"),
                "poverty_rate":        round(poverty_rate, 4),
                "snap_rate":           round(snap_rate, 4),
                "vulnerability_score": vulnerability,
            })

        counties.sort(key=lambda x: x["vulnerability_score"], reverse=True)

        return _ok("census_acs", {
            "state_fips":   state_fips,
            "county_count": len(counties),
            "counties":     counties,
            "fetched_at":   datetime.utcnow().isoformat() + "Z",
        })
    except Exception as e:
        return _err("census_acs", f"Parse error: {e}")


# =============================================================================
# 7. USDA LOCAL FOOD PORTAL — farmers markets + food hubs (KEY REQUIRED)
# =============================================================================

def fetch_local_food_resources(state: str = "Louisiana") -> dict:
    """
    Farmers markets and food hubs from USDA Local Food Portal.
    Latency: semi-static (updated periodically).
    Get your free key by emailing: localfoodportal@ams.usda.gov
    """
    if not USDA_FOOD_KEY:
        return _err("usda_local_food", "USDA_FOOD_KEY not set in environment")

    results   = {"farmers_markets": [], "food_hubs": []}
    endpoints = {
        "farmers_markets": "https://www.usdalocalfoodportal.com/api/farmersmarket/",
        "food_hubs":       "https://www.usdalocalfoodportal.com/api/foodhub/",
    }

    for kind, url in endpoints.items():
        r = _get(url, params={"apikey": USDA_FOOD_KEY, "location_state": state}, timeout=20)
        if r is None:
            continue
        try:
            for item in r.json():
                results[kind].append({
                    "name":    item.get("listing_name"),
                    "city":    item.get("location_city"),
                    "state":   item.get("location_state"),
                    "zip":     item.get("location_zipcode"),
                    "website": item.get("media_website"),
                })
        except Exception as e:
            print(f"  [WARN] {kind} parse error: {e}")

    total = len(results["farmers_markets"]) + len(results["food_hubs"])
    if total == 0:
        return _err("usda_local_food", "No resources returned for state")

    return _ok("usda_local_food", {
        "state":                state,
        "farmers_market_count": len(results["farmers_markets"]),
        "food_hub_count":       len(results["food_hubs"]),
        "supply_access_score":  round(min(total / 100, 1.0), 4),
        "farmers_markets":      results["farmers_markets"],
        "food_hubs":            results["food_hubs"],
        "fetched_at":           datetime.utcnow().isoformat() + "Z",
    })


# =============================================================================
# 8. NOAA CDO — precipitation anomaly by station (KEY REQUIRED)
# =============================================================================

def fetch_noaa_precip_anomaly(station_id: str = "GHCND:USW00012960",
                               days_back: int = 30) -> dict:
    """
    NOAA Climate Data Online — daily precipitation for a weather station.
    Latency: 24-48 hour lag on daily observations.
    Louisiana stations:
      USW00012960 = New Orleans Intl Airport
      USW00013970 = Baton Rouge Metro Airport
      USW00013957 = Lake Charles Regional
      USW00013995 = Shreveport Regional
    Get your free key at: https://www.ncdc.noaa.gov/cdo-web/token
    """
    if not NOAA_CDO_KEY:
        return _err("noaa_cdo", "NOAA_CDO_KEY not set in environment")

    end_date   = datetime.utcnow().strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    url    = "https://www.ncdc.noaa.gov/cdo-web/api/v2/data"
    params = {
        "datasetid":  "GHCND",
        "stationid":  station_id,
        "datatypeid": "PRCP",
        "startdate":  start_date,
        "enddate":    end_date,
        "limit":      days_back,
        "units":      "metric",
    }

    r = _get(url, params=params, headers={"token": NOAA_CDO_KEY}, timeout=25)
    if r is None:
        return _err("noaa_cdo", "Request failed")

    try:
        results = r.json().get("results", [])
        if not results:
            return _partial("noaa_cdo", {}, "No precipitation data returned for station")

        precip_mm = [rec["value"] / 10.0 for rec in results if "value" in rec]
        dates     = [rec["date"][:10]    for rec in results if "value" in rec]
        total_mm  = sum(precip_mm)
        avg_daily = total_mm / len(precip_mm) if precip_mm else 0

        LOUISIANA_30DAY_NORMAL_MM = 120.0
        anomaly_pct = ((total_mm - LOUISIANA_30DAY_NORMAL_MM)
                        / LOUISIANA_30DAY_NORMAL_MM) * 100

        return _ok("noaa_cdo", {
            "station_id":      station_id,
            "start_date":      start_date,
            "end_date":        end_date,
            "total_precip_mm": round(total_mm, 2),
            "avg_daily_mm":    round(avg_daily, 2),
            "anomaly_pct":     round(anomaly_pct, 2),
            "daily_series":    dict(zip(dates, [round(v, 2) for v in precip_mm])),
            "fetched_at":      datetime.utcnow().isoformat() + "Z",
        })
    except Exception as e:
        return _err("noaa_cdo", f"Parse error: {e}")


# =============================================================================
# MASTER FETCH — pull all sources for a community centroid
# =============================================================================

def fetch_all_for_community(lat: float, lon: float,
                             state: str = "LA",
                             state_fips: str = "22",
                             state_full: str = "Louisiana") -> dict:
    """
    Run all fetchers for a community centroid and return a combined payload.
    This is what B3's risk scorer calls.

    Example:
        payload = fetch_all_for_community(29.95, -90.07)  # New Orleans
    """
    print(f"\n[FPI Fetch] lat={lat}, lon={lon}, state={state}")

    results = {}

    print("  Fetching Open-Meteo weather...")
    results["weather"] = fetch_open_meteo(lat, lon)

    print("  Fetching NOAA weather alerts...")
    results["alerts"] = fetch_noaa_alerts(state)

    print("  Fetching FEMA disaster declarations...")
    results["disasters"] = fetch_fema_disasters(state)

    print("  Fetching VegScape NDVI...")
    results["ndvi"] = fetch_vegscape_ndvi(lat, lon)

    if NASS_API_KEY:
        print("  Fetching NASS QuickStats...")
        results["crop_stats"] = fetch_nass_quickstats(state)
    else:
        print("  [SKIP] NASS QuickStats — key not set")
        results["crop_stats"] = _err("nass_quickstats", "Key not configured")

    if CENSUS_API_KEY:
        print("  Fetching Census ACS vulnerability...")
        results["vulnerability"] = fetch_census_vulnerability(state_fips)
    else:
        print("  [SKIP] Census ACS — key not set")
        results["vulnerability"] = _err("census_acs", "Key not configured")

    if USDA_FOOD_KEY:
        print("  Fetching USDA local food resources...")
        results["local_food"] = fetch_local_food_resources(state_full)
    else:
        print("  [SKIP] USDA Local Food — key not set")
        results["local_food"] = _err("usda_local_food", "Key not configured")

    if NOAA_CDO_KEY:
        print("  Fetching NOAA CDO precip anomaly...")
        results["precip_anomaly"] = fetch_noaa_precip_anomaly()
    else:
        print("  [SKIP] NOAA CDO — key not set")
        results["precip_anomaly"] = _err("noaa_cdo", "Key not configured")

    ok_count = sum(1 for v in results.values() if v["status"] == "ok")
    print(f"\n[FPI Fetch] Done — {ok_count}/{len(results)} sources OK")
    return results


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    TEST_LAT, TEST_LON = 29.95, -90.07  # New Orleans Lower 9th Ward

    print("=" * 60)
    print("Testing no-key endpoints (New Orleans centroid)")
    print("=" * 60)

    print("\n--- Open-Meteo ---")
    r = fetch_open_meteo(TEST_LAT, TEST_LON)
    print(f"Status: {r['status']}")
    if r["status"] == "ok":
        print(f"  Temp:          {r['data']['current_temp_c']}C")
        print(f"  Soil moisture: {r['data']['soil_moisture_m3m3']} m3/m3")
        print(f"  24h precip:    {r['data']['precip_24h_mm']} mm")

    print("\n--- NOAA Alerts ---")
    r = fetch_noaa_alerts("LA")
    print(f"Status: {r['status']}")
    if r["status"] == "ok":
        print(f"  Active alerts:    {r['data']['active_count']}")
        print(f"  Max severity:     {r['data']['max_severity_score']}")

    print("\n--- OpenFEMA ---")
    r = fetch_fema_disasters("LA")
    print(f"Status: {r['status']}")
    if r["status"] == "ok":
        print(f"  Recent disasters: {r['data']['total_recent']}")
        print(f"  Active:           {r['data']['active_count']}")

    print("\n--- VegScape NDVI ---")
    r = fetch_vegscape_ndvi(TEST_LAT, TEST_LON)
    print(f"Status: {r['status']}")
    print(f"  Source:    {r['data'].get('source_endpoint', 'n/a')}")
    print(f"  NDVI:      {r['data'].get('ndvi')}")
    print(f"  ET proxy:  {r['data'].get('et0_mm_day')}")
    if r.get("error"):
        print(f"  Note: {r['error']}")

    print("\n--- NASS QuickStats ---")
    r = fetch_nass_quickstats("LA", commodity="RICE")  # rice is reliable for LA
    print(f"Status: {r['status']}")
    if r["status"] == "ok":
        print(f"  Records returned: {len(r['data']['records'])}")
        if r['data']['records']:
            print(f"  Sample: {r['data']['records'][0]}")

    print("\n--- Census ACS ---")
    r = fetch_census_vulnerability("22")
    print(f"Status: {r['status']}")
    if r["status"] == "ok":
        print(f"  Counties: {r['data']['county_count']}")
        print(f"  Most vulnerable: {r['data']['counties'][0]['county_name']}")

    print("\n--- NOAA CDO ---")
    r = fetch_noaa_precip_anomaly()
    print(f"Status: {r['status']}")
    if r["status"] == "ok":
        print(f"  30-day total: {r['data']['total_precip_mm']} mm")
        print(f"  Anomaly: {r['data']['anomaly_pct']}%")