import requests
import math
import os
import json
import random
from datetime import datetime
from django.core.cache import cache
from main.models import ParkingZoneSegment
import pytz

# Melbourne Open Data API (real-time parking bay sensors)
PARKING_API = (
    "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/"
    "on-street-parking-bay-sensors/records?limit=100&order_by=status_timestamp%20DESC"
)

# Melbourne CBD coordinates (used for distance calculation)
CBD_COORDS = (-37.814, 144.96332)

# Predefined dates for special adjustments (e.g., city events)
SPECIAL_DATES = [
    (2025, 8, 15),
    (2025, 9, 5)
]

# Load cached street name mapping (Zone ID → Street name)
STREET_CACHE_FILE = os.path.join(os.path.dirname(__file__), "street_cache.json")
USE_IDX_FOR_CACHE = False  # Flag to control lookup method

if os.path.exists(STREET_CACHE_FILE):
    try:
        with open(STREET_CACHE_FILE, "r", encoding="utf-8") as f:
            STREET_CACHE = json.load(f)
        USE_IDX_FOR_CACHE = True
        print(f"[INFO] STREET_CACHE loaded from JSON: {len(STREET_CACHE)} entries")
    except Exception as e:
        STREET_CACHE = {}
        print("[WARN] Failed to load STREET_CACHE from JSON:", e)
else:
    try:
        segments = ParkingZoneSegment.objects.all().values("parking_zone", "on_street")
        STREET_CACHE = {}
        for seg in segments:
            zone = str(seg["parking_zone"])
            if zone not in STREET_CACHE:
                STREET_CACHE[zone] = seg["on_street"]
        USE_IDX_FOR_CACHE = False
        print(f"[INFO] STREET_CACHE built from DB: {len(STREET_CACHE)} entries")
    except Exception as e:
        STREET_CACHE = {}
        print("[WARN] Failed to build STREET_CACHE from DB:", e)

# Haversine formula: calculates distance between two lat/lng points (meters)
def calc_distance(lat1, lng1, lat2, lng2):
    R = 6371000
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# Simple status badge based on occupancy ratio
def status_badge(available, total):
    ratio = (available / total) if total else 0
    if ratio < 0.3:
        return "red"
    elif ratio < 0.7:
        return "yellow"
    return "green"


# Group nearby points into clusters
def group_by_proximity(records, radius_m=100):
    clusters = []
    for rec in records:
        loc = rec.get("location")
        if not loc:
            continue
        lat, lng = loc["lat"], loc["lon"]
        added = False
        for cluster in clusters:
            if calc_distance(lat, lng, cluster["lat"], cluster["lng"]) <= radius_m:
                cluster["points"].append(rec)
                added = True
                break
        if not added:
            clusters.append({"lat": lat, "lng": lng, "points": [rec]})
    return clusters


# Assign plausible total spaces to each cluster
def estimate_total_spaces(real_total, lat, lng):
    dist = calc_distance(lat, lng, *CBD_COORDS)
    if real_total >= 30:
        return random.randint(30, 40)
    elif dist <= 500:
        return random.randint(20, 30)
    else:
        return random.randint(10, 20)


# Adjust availability based on time of day and weekday/weekend
def adjust_by_time(base_avail, total):
    tz = pytz.timezone("Australia/Melbourne")
    now = datetime.now(tz)
    h = now.hour
    weekday = now.weekday()

    if weekday < 5 and (6 <= h <= 11 or 12 <= h <= 17):
        factor = random.uniform(0.4, 0.7)
    elif weekday < 5:
        factor = random.uniform(0.7, 1.0)
    else:
        factor = random.uniform(0.3, 0.6)

    return min(total, max(0, int(base_avail * factor)))


# Adjust for higher demand near CBD
def adjust_for_cbd_demand(avail, total, lat, lng):
    dist = calc_distance(lat, lng, *CBD_COORDS)
    if dist <= 1000:
        factor = random.uniform(0.6, 0.85)
        return min(total, max(0, int(avail * factor)))
    return avail


# Adjust for specific special event dates
def adjust_for_special_dates(avail, total, lat, lng):
    tz = pytz.timezone("Australia/Melbourne")
    today = datetime.now(tz).date()
    if any(today.year == y and today.month == m and today.day == d for y, m, d in SPECIAL_DATES):
        if calc_distance(lat, lng, *CBD_COORDS) <= 10000:
            factor = random.uniform(0.3, 0.6)
            return min(total, max(0, int(avail * factor)))
    return avail


# Add small natural variation to avoid static values
def apply_random_variation(avail, total):
    change = random.choice([-2, -1, 0, 1, 2])
    return min(total, max(0, avail + change))


# Main function: fetch API, apply adjustments, and cache results
def fetch_and_cache_parking():
    try:
        resp = requests.get(PARKING_API, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("results", [])
        clusters = group_by_proximity(data)

        prev_data = cache.get("prev_availability") or {}
        prev_totals = cache.get("prev_totals") or {}
        refresh_counter = cache.get("refresh_counter") or {}
        parking_list = []

        for idx, cluster in enumerate(clusters, start=1):
            real_total = len(cluster["points"])
            real_available = sum(
                1 for p in cluster["points"] if p.get("status_description", "").lower() == "unoccupied"
            )

            total_spaces = prev_totals.get(idx) or estimate_total_spaces(real_total, cluster["lat"], cluster["lng"])

            base_avail = min(total_spaces, max(0, real_available + random.randint(-1, 3)))
            base_avail = adjust_by_time(base_avail, total_spaces)
            base_avail = adjust_for_cbd_demand(base_avail, total_spaces, cluster["lat"], cluster["lng"])
            base_avail = apply_random_variation(base_avail, total_spaces)

            counter = refresh_counter.get(idx, 0)
            threshold = 5 if random.random() < 0.8 else 1
            if counter < threshold and idx in prev_data:
                available = prev_data[idx]
                refresh_counter[idx] = counter + 1
            else:
                available = base_avail
                refresh_counter[idx] = 1

            # Street name selection logic
            if USE_IDX_FOR_CACHE:
                street_name = STREET_CACHE.get(str(idx), "Melbourne CBD")
            else:
                if cluster["points"]:
                    zone_number = str(cluster["points"][0].get("zone_number", ""))
                    street_name = STREET_CACHE.get(zone_number, "Melbourne CBD")
                else:
                    street_name = "Melbourne CBD"

            dist_m = calc_distance(cluster["lat"], cluster["lng"], *CBD_COORDS)
            dist_label = f"{dist_m/1000:.1f}km" if dist_m >= 1000 else f"{int(dist_m)}m"
            walk_time = max(1, round((dist_m / 1000) * 12))

            prev_avail = prev_data.get(idx)
            if prev_avail is None:
                trend = "stable"
            elif available > prev_avail:
                trend = "increasing"
            elif available < prev_avail:
                trend = "decreasing"
            else:
                trend = "stable"

            parking_list.append({
                "name": f"Parking Zone {idx}",
                "address": street_name,
                "lat": cluster["lat"],
                "lng": cluster["lng"],
                "available": available,
                "total": total_spaces,
                "distance": dist_label,
                "prediction": trend,
                "walkTime": f"{walk_time} min",
                "badge": status_badge(available, total_spaces)
            })

        # Always store in idx order
        parking_list.sort(key=lambda x: int(x["name"].split()[-1]))

        cache.set("live_parking_data", parking_list, timeout=60)
        cache.set("prev_availability", {i+1: s["available"] for i, s in enumerate(parking_list)}, timeout=3600)
        cache.set("prev_totals", {i+1: s["total"] for i, s in enumerate(parking_list)}, timeout=86400)
        cache.set("refresh_counter", refresh_counter, timeout=86400)

    except Exception as e:
        print("[ERROR] Unable to update parking data:", e)


# Public API to retrieve cached data
def get_live_parking_data():
    return cache.get("live_parking_data") or []
