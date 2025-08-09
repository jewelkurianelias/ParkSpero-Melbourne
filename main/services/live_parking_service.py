import requests
import math
import os
import json
import random
from datetime import datetime
from django.core.cache import cache
import pytz

API_URL = (
    "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/"
    "on-street-parking-bay-sensors/records?limit=100&order_by=status_timestamp%20DESC"
)

CITY_CENTER = (-37.814, 144.96332)
HIGH_DEMAND_RADIUS = 1000
EVENT_DATES = [
    (2025, 8, 15),
    (2025, 9, 5)
]

# 讀取 Zone 對應路名的 street_cache.json
STREET_CACHE_PATH = os.path.join(os.path.dirname(__file__), "street_cache.json")
if os.path.exists(STREET_CACHE_PATH):
    with open(STREET_CACHE_PATH, "r", encoding="utf-8") as f:
        STREET_CACHE = json.load(f)  # { "1": "Street A", "2": "Street B", ... }
else:
    STREET_CACHE = {}

def haversine(lat1, lng1, lat2, lng2):
    R = 6371000
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def _badge_by_percent(available, total):
    percent = (available / total) if total else 0
    if percent < 0.3:
        return "red"
    elif percent < 0.7:
        return "yellow"
    return "green"

def cluster_sites(records, radius_m=100):
    clusters = []
    for rec in records:
        loc = rec.get("location")
        if not loc:
            continue
        lat, lng = loc["lat"], loc["lon"]
        assigned = False
        for cluster in clusters:
            dist = haversine(lat, lng, cluster["lat"], cluster["lng"])
            if dist <= radius_m:
                cluster["points"].append(rec)
                assigned = True
                break
        if not assigned:
            clusters.append({
                "lat": lat,
                "lng": lng,
                "points": [rec]
            })
    return clusters

def _assign_total_spaces(total_real, lat, lng):
    dist = haversine(lat, lng, *CITY_CENTER)
    if total_real >= 30:
        return random.randint(30, 40)
    elif dist <= 500:
        return random.randint(20, 30)
    else:
        return random.randint(10, 20)

def _time_weight_adjustment(base_available, total):
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
    return min(total, max(0, int(base_available * factor)))

def _high_demand_adjustment(available, total, lat, lng):
    dist = haversine(lat, lng, *CITY_CENTER)
    if dist <= HIGH_DEMAND_RADIUS:
        factor = random.uniform(0.6, 0.85)
        return min(total, max(0, int(available * factor)))
    return available

def _event_day_adjustment(available, total, lat, lng):
    tz = pytz.timezone("Australia/Melbourne")
    today = datetime.now(tz).date()
    if any(today.year == y and today.month == m and today.day == d for y, m, d in EVENT_DATES):
        dist = haversine(lat, lng, *CITY_CENTER)
        if dist <= 10000:
            factor = random.uniform(0.3, 0.6)
            return min(total, max(0, int(available * factor)))
    return available

def _natural_fluctuation(available, total):
    change = random.choice([-2, -1, 0, 1, 2])
    return min(total, max(0, available + change))

def fetch_and_cache_parking():
    try:
        resp = requests.get(API_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("results", [])
        clusters = cluster_sites(data)

        prev_data = cache.get("prev_parking_data") or {}
        prev_totals = cache.get("prev_parking_totals") or {}
        refresh_counter = cache.get("parking_refresh_counter") or {}
        parking_spots = []

        for i, cluster in enumerate(clusters, start=1):
            total_real = len(cluster["points"])
            available_real = sum(
                1 for p in cluster["points"] if p.get("status_description", "").lower() == "unoccupied"
            )

            total = prev_totals.get(i)
            if total is None or total == 0:
                total = _assign_total_spaces(total_real, cluster["lat"], cluster["lng"])

            base_available = min(total, max(0, available_real + random.randint(-1, 3)))
            base_available = _time_weight_adjustment(base_available, total)
            base_available = _high_demand_adjustment(base_available, total, cluster["lat"], cluster["lng"])
            #base_available = _event_day_adjustment(base_available, total, cluster["lat"], cluster["lng"])
            base_available = _natural_fluctuation(base_available, total)

            counter = refresh_counter.get(i, 0)
            change_threshold = 5 if random.random() < 0.8 else 1
            if counter < change_threshold and i in prev_data:
                available = prev_data[i]
                refresh_counter[i] = counter + 1
            else:
                available = base_available
                refresh_counter[i] = 1

            name = f"Parking Zone {i}"

            # 🚀 直接從 JSON 快取取路名
            address = STREET_CACHE.get(str(i), "Melbourne CBD")

            dist_m = haversine(cluster["lat"], cluster["lng"], *CITY_CENTER)
            distance = f"{dist_m/1000:.1f}km" if dist_m >= 1000 else f"{int(dist_m)}m"
            walk_min = max(1, round((dist_m / 1000) * 12))

            prev_avail = prev_data.get(i)
            if prev_avail is None:
                prediction = "stable"
            elif available > prev_avail:
                prediction = "increasing"
            elif available < prev_avail:
                prediction = "decreasing"
            else:
                prediction = "stable"

            parking_spots.append({
                "name": name,
                "address": address,
                "lat": cluster["lat"],
                "lng": cluster["lng"],
                "available": available,
                "total": total,
                "distance": distance,
                "prediction": prediction,
                "walkTime": f"{walk_min} min",
                "badge": _badge_by_percent(available, total)
            })

        cache.set("live_parking_data", parking_spots, timeout=60)
        cache.set("prev_parking_data", {i+1: s["available"] for i, s in enumerate(parking_spots)}, timeout=3600)
        cache.set("prev_parking_totals", {i+1: s["total"] for i, s in enumerate(parking_spots)}, timeout=86400)
        cache.set("parking_refresh_counter", refresh_counter, timeout=86400)

    except Exception as e:
        print("[ERROR] Failed to fetch parking data:", e)

def get_live_parking_data():
    return cache.get("live_parking_data") or []
