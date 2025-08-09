# services/build_street_cache_by_zone.py
import os
import json
import math
import requests
from datetime import datetime
import pytz
import random

API_URL = (
    "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/"
    "on-street-parking-bay-sensors/records?limit=100&order_by=status_timestamp%20DESC"
)
CITY_CENTER = (-37.814, 144.96332)

# ==== Helper functions ====
def haversine(lat1, lng1, lat2, lng2):
    R = 6371000
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng/2)**2
    return 2 * R * math.asin(math.sqrt(a))

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

def _reverse_geocode(lat, lng):
    """Call Nominatim to get street + suburb"""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "json", "zoom": 18, "addressdetails": 1},
            headers={"User-Agent": "MelbParkingApp/1.0"},
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        road = data.get("address", {}).get("road", "")
        suburb = data.get("address", {}).get("suburb", "")
        address = f"{road}, {suburb}" if road else suburb or "Melbourne CBD"
    except Exception as e:
        print(f"[WARN] Reverse geocode failed for {lat},{lng}: {e}")
        address = "Melbourne CBD"
    return address

# ==== Main script ====
def build_cache():
    print("[INFO] Fetching parking data from API...")
    resp = requests.get(API_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("results", [])
    clusters = cluster_sites(data)

    street_cache = {}
    for i, cluster in enumerate(clusters, start=1):
        lat, lng = cluster["lat"], cluster["lng"]
        address = _reverse_geocode(lat, lng)
        street_cache[str(i)] = address
        print(f"[OK] Zone {i} -> {address}")

    # Save JSON
    save_path = os.path.join(os.path.dirname(__file__), "street_cache.json")
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(street_cache, f, ensure_ascii=False, indent=2)
    print(f"[DONE] Saved street cache to {save_path}")

if __name__ == "__main__":
    build_cache()
