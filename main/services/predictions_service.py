# main/services/predictions_service.py
from __future__ import annotations

import os
import math
import time
import requests
from datetime import datetime, time as dtime
from typing import Dict, List, Optional, Tuple
import pytz
from django.core.cache import cache

# ---- Socrata endpoints ----
SENSORS_API = (
    "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/"
    "on-street-parking-bay-sensors/records"
)
SIGN_PLATES_API = (
    "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/"
    "sign-plates-located-in-each-parking-zone/records"
)
SEGMENTS_API = (
    "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/"
    "parking-zones-linked-to-street-segments/records"
)

MELB_TZ = pytz.timezone("Australia/Melbourne")
APP_TOKEN = os.getenv("MELB_APP_TOKEN")  # optional but recommended

# Cache TTLs (seconds)
SIGN_PLATES_TTL = 60 * 30  # 30 min
SEGMENTS_TTL = 60 * 60     # 1 h
PREDICTIONS_TTL = 60       # 1 min

HEADERS = {"Accept": "application/json"}
if APP_TOKEN:
    HEADERS["X-App-Token"] = APP_TOKEN


# ---------- Utilities ----------

DAY_TO_IDX = {
    "MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6
}

def _parse_time(s: Optional[str]) -> dtime:
    # Socrata times like "07:30:00" or null
    if not s:
        return dtime(0, 0, 0)
    hh, mm, ss = (int(x) for x in s.split(":"))
    return dtime(hh, mm, ss)

def _expand_days(spec: Optional[str]) -> List[int]:
    """
    Parse strings like 'Mon-Fri', 'Mon,Wed,Fri', 'Sat', 'Sun', 'Mon-Sun'.
    Returns list of weekday indices (Mon=0).
    """
    if not spec:
        return list(range(7))  # assume daily if missing

    spec = spec.upper().replace(" ", "")
    spec = spec.replace("PUBLICHOLIDAYS", "")  # ignore extra text if present

    if spec in ("DAILY", "EVERYDAY", "MON-SUN"):
        return list(range(7))

    days: List[int] = []
    parts = spec.split(",")
    for p in parts:
        if "-" in p:
            a, b = p.split("-")
            a_idx = DAY_TO_IDX.get(a[:3], None)
            b_idx = DAY_TO_IDX.get(b[:3], None)
            if a_idx is None or b_idx is None:
                continue
            if a_idx <= b_idx:
                days.extend(range(a_idx, b_idx + 1))
            else:
                # wrap-around like "FRI-MON"
                days.extend(list(range(a_idx, 7)) + list(range(0, b_idx + 1)))
        else:
            idx = DAY_TO_IDX.get(p[:3], None)
            if idx is not None:
                days.append(idx)
    # De-dup while preserving order
    seen = set()
    out = []
    for d in days:
        if d not in seen:
            out.append(d); seen.add(d)
    return out or list(range(7))


def _minutes_for_code(code: str) -> Tuple[Optional[int], str]:
    """
    Map restriction_display -> (minutes, kind).
    kind is one of: 'PERMIT', 'LIMITED', 'FREE', 'LOADING', 'METERED', 'UNKNOWN'
    """
    if not code:
        return None, "UNKNOWN"

    u = code.strip().upper()

    # Permit-only zones
    if "PERMIT" in u or u == "PP":
        return None, "PERMIT"

    # Loading zones like LZ30 / LZ15
    if u.startswith("LZ"):
        try:
            return int(u[2:]), "LOADING"
        except Exception:
            return None, "LOADING"

    # Free parking with minutes or 2P (e.g., FP15, FP2P)
    if u.startswith("FP"):
        if u.endswith("P") and len(u) >= 3 and u[2].isdigit():
            return int(u[2]) * 60, "FREE"
        # FP + minutes
        digits = "".join(ch for ch in u if ch.isdigit())
        return (int(digits) if digits else None), "FREE"

    # Metered parking like MP1P / MP2P / MP3P
    if u.startswith("MP") and u.endswith("P") and len(u) >= 4 and u[2].isdigit():
        return int(u[2]) * 60, "METERED"

    # Generic 1P/2P/3P/4P, etc.
    if u.endswith("P") and u[0].isdigit():
        try:
            return int(u[0]) * 60, "LIMITED"
        except Exception:
            pass

    # Fallback: try to read trailing digits as minutes (rare)
    digits = "".join(ch for ch in u if ch.isdigit())
    return (int(digits) if digits else None), "UNKNOWN"


def _restriction_active(days_spec: Optional[str],
                        start: Optional[str],
                        finish: Optional[str],
                        now_melb: datetime) -> bool:
    day_ok = now_melb.weekday() in _expand_days(days_spec)
    if not day_ok:
        return False
    t0 = _parse_time(start)
    t1 = _parse_time(finish)
    now_t = now_melb.time()
    if t0 <= t1:
        return t0 <= now_t <= t1
    # window crosses midnight
    return now_t >= t0 or now_t <= t1


def _socrata_get_all(url: str, extra_params: Dict[str, str] | None = None,
                     limit: int = 100, max_pages: int = 20) -> List[dict]:
    """
    Page through Socrata V2.1 records.
    """
    params = {"limit": str(limit)}
    if extra_params:
        params.update({k: str(v) for k, v in extra_params.items()})

    results: List[dict] = []
    offset = 0
    for _ in range(max_pages):
        p = dict(params)
        p["offset"] = str(offset)
        r = requests.get(url, params=p, headers=HEADERS, timeout=15)
        r.raise_for_status()
        chunk = r.json().get("results", [])
        if not chunk:
            break
        results.extend(chunk)
        if len(chunk) < limit:
            break
        offset += limit
        # be polite
        time.sleep(0.15)
    return results


# ---------- Metadata loaders (cached) ----------

def _load_sign_plates() -> Dict[int, List[dict]]:
    """
    Returns: { parkingzone: [ {display, days, start, finish}, ... ] }
    Cached to reduce API calls.
    """
    cache_key = "signplates:v1"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    plates = _socrata_get_all(SIGN_PLATES_API, extra_params={"order_by": "parkingzone"})
    by_zone: Dict[int, List[dict]] = {}
    for p in plates:
        z = p.get("parkingzone")
        if z is None:
            continue
        rec = {
            "display": p.get("restriction_display"),
            "days": p.get("restriction_days"),
            "start": p.get("time_restrictions_start"),
            "finish": p.get("time_restrictions_finish"),
        }
        by_zone.setdefault(int(z), []).append(rec)

    cache.set(cache_key, by_zone, SIGN_PLATES_TTL)
    return by_zone


def _load_segments() -> Dict[int, dict]:
    """
    Optional helper: map zone -> street label (for UI).
    Returns: { parkingzone: {"onstreet": str, "streetfrom": str, "streetto": str} }
    """
    cache_key = "segments:v1"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    segs = _socrata_get_all(SEGMENTS_API, extra_params={"order_by": "parkingzone"})
    by_zone: Dict[int, dict] = {}
    for s in segs:
        z = s.get("parkingzone")
        if z is None:
            continue
        by_zone[int(z)] = {
            "onstreet": s.get("onstreet"),
            "streetfrom": s.get("streetfrom"),
            "streetto": s.get("streetto"),
        }

    cache.set(cache_key, by_zone, SEGMENTS_TTL)
    return by_zone


# ---------- Core prediction logic ----------

def _active_rule_minutes(zone: Optional[int], now_melb: datetime) -> Tuple[Optional[int], Optional[str]]:
    """
    For a zone at 'now', choose the most restrictive active rule.
    Returns (minutes_allowed, rule_code) where rule_code is the original display.
    If no active rule, returns (None, None).
    """
    if zone is None:
        return None, None
    plates = _load_sign_plates().get(int(zone), [])
    best_minutes: Optional[int] = None
    best_code: Optional[str] = None

    for rec in plates:
        if not _restriction_active(rec.get("days"), rec.get("start"), rec.get("finish"), now_melb):
            continue

        minutes, kind = _minutes_for_code(rec.get("display", ""))
        # Permit zones are a distinct class
        if kind == "PERMIT":
            return None, "PP"

        if minutes is None:
            # If minutes cannot be parsed (unknown), ignore for timing
            continue

        if best_minutes is None or minutes < best_minutes:
            best_minutes = minutes
            best_code = rec.get("display")

    return best_minutes, best_code


def _classify_present(elapsed_min: float,
                      allowed_min: Optional[int],
                      rule_code: Optional[str]) -> str:
    """
    Map remaining time to one of the five 'occupied' classes
    (the sixth class 'UNOCCUPIED' is handled elsewhere).
    """
    if rule_code == "PP":
        return "PERMIT_PARKING"

    if allowed_min is None:
        # No active restriction right now -> we can't bound it; assume > 1h
        return "OCCUPIED_GT_60M"

    remaining = allowed_min - elapsed_min
    if remaining <= 15:
        return "VACATE_15M"
    if remaining <= 30:
        return "VACATE_30M"
    if remaining <= 60:
        return "VACATE_60M"
    return "OCCUPIED_GT_60M"


def _parse_iso_to_melb(ts: str) -> datetime:
    # "2025-04-14T03:01:40+00:00"
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.astimezone(MELB_TZ)


def predict_now() -> dict:
    """
    Compute predictions for all bays, bucketed into six classes.
    Returns a JSON-serialisable dict:
    {
      "generated_at": "...",
      "ttl": 60,
      "counts": {class: n, ...},
      "items": [
         {
           "kerbsideid": 123,
           "zone_number": 7003,
           "status": "Present" | "Unoccupied" | "Unknown",
           "status_timestamp": "...",
           "classification": "... one of the six ...",
           "minutes_elapsed": 42.5,
           "allowed_minutes": 60,
           "restriction_code": "1P" | "PP" | "MP2P" | None,
           "street": "Pelham Street (Cardigan–Swanston)" | None
         }, ...
      ]
    }
    """
    # Serve cached predictions if still fresh
    cached = cache.get("predictions:v1")
    if cached:
        return cached

    now_melb = datetime.now(MELB_TZ)
    segments = _load_segments()  # optional; only for labels

    # Pull all sensor rows (sorted by latest status change first)
    sensors = _socrata_get_all(
        SENSORS_API,
        extra_params={"order_by": "status_timestamp DESC"},
        limit=100,
        max_pages=10,
    )

    counts = {
        "UNOCCUPIED": 0,
        "VACATE_15M": 0,
        "VACATE_30M": 0,
        "VACATE_60M": 0,
        "OCCUPIED_GT_60M": 0,
        "PERMIT_PARKING": 0,
    }

    items: List[dict] = []

    for rec in sensors:
        status = (rec.get("status_description") or "").strip().title()  # Present / Unoccupied / Unknown
        zone = rec.get("zone_number")
        kerb = rec.get("kerbsideid")
        ts = rec.get("status_timestamp")

        # Build a friendly street label if available
        street_label = None
        if zone is not None and int(zone) in segments:
            s = segments[int(zone)]
            if s.get("onstreet"):
                if s.get("streetfrom") and s.get("streetto"):
                    street_label = f"{s['onstreet']} ({s['streetfrom']}–{s['streetto']})"
                else:
                    street_label = s["onstreet"]

        if status.lower() == "unoccupied":
            classification = "UNOCCUPIED"
            minutes_elapsed = 0.0
            allowed_min = None
            rule_code = None
        else:
            # Treat anything not 'Unoccupied' as Present for this task
            dt_melb = _parse_iso_to_melb(ts) if ts else now_melb
            elapsed_min = (now_melb - dt_melb).total_seconds() / 60.0
            allowed_min, rule_code = _active_rule_minutes(zone, now_melb)
            classification = _classify_present(elapsed_min, allowed_min, rule_code)
            minutes_elapsed = round(elapsed_min, 2)

        counts[classification] += 1

        items.append({
            "kerbsideid": kerb,
            "zone_number": zone,
            "status": status or "Unknown",
            "status_timestamp": ts,
            "classification": classification,
            "minutes_elapsed": minutes_elapsed,
            "allowed_minutes": allowed_min,
            "restriction_code": rule_code,
            "street": street_label,
        })

    payload = {
        "generated_at": now_melb.isoformat(),
        "ttl": PREDICTIONS_TTL,
        "counts": counts,
        "items": items,
    }

    cache.set("predictions:v1", payload, PREDICTIONS_TTL)
    return payload
