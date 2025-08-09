import pandas as pd
from django.http import JsonResponse
from django.conf import settings
import os

def parking_chart_data(request):
    csv_path = os.path.join(settings.STATICFILES_DIRS[0], "data1.csv")
    df = pd.read_csv(csv_path)

    df.columns = [c.strip() for c in df.columns]
    df["hour"] = df["timestamp"].astype(str).str.split(":").str[0].astype(int)

    def get_time_of_day(h):
        if 6 <= h <= 11:
            return "Morning"
        elif 12 <= h <= 17:
            return "Afternoon"
        elif 18 <= h <= 23:
            return "Evening"
        else:
            return "Night"

    df["TimeOfDay"] = df["hour"].apply(get_time_of_day)

    weekly_list = []
    for (day, tod), group in df.groupby(["day", "TimeOfDay"]):
        total = int(len(group))
        available = int((group["Status_Description"].str.lower() == "unoccupied").sum())
        availability_pct = float(round((available / total) * 100, 2)) if total else 0.0
        demand_pct = float(round(100 - availability_pct, 2))
        weekly_list.append({
            "day": str(day)[:3],
            "timeOfDay": str(tod),
            "availability": availability_pct,
            "demand": demand_pct
        })

    hourly_list = []
    for (day, hour), group in df.groupby(["day", "hour"]):
        total = int(len(group))
        available = int((group["Status_Description"].str.lower() == "unoccupied").sum())
        availability_pct = float(round((available / total) * 100, 2)) if total else 0.0
        hourly_list.append({
            "day": str(day)[:3],
            "hour": int(hour),
            "availability": availability_pct
        })

    return JsonResponse({
        "weeklyData": weekly_list,
        "hourlyData": hourly_list
    })
