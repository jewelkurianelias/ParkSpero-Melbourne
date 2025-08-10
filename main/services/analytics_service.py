from django.http import JsonResponse
from main.models import OnStreetParkingBaySensor
import pandas as pd

def parking_chart_data(request):

    queryset = OnStreetParkingBaySensor.objects.all().values(
        'day', 'status_timestamp', 'status_description'
    )
    df = pd.DataFrame(list(queryset))


    df["hour"] = pd.to_datetime(df["status_timestamp"]).dt.hour


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

    # Weekly Data
    weekly_list = []
    for (day, tod), group in df.groupby(["day", "TimeOfDay"]):
        total = len(group)
        available = (group["status_description"].str.lower() == "unoccupied").sum()
        availability_pct = round((available / total) * 100, 2) if total else 0.0
        demand_pct = round(100 - availability_pct, 2)
        weekly_list.append({
            "day": str(day)[:3],
            "timeOfDay": tod,
            "availability": availability_pct,
            "demand": demand_pct
        })

    # Hourly Data
    hourly_list = []
    for (day, hour), group in df.groupby(["day", "hour"]):
        total = len(group)
        available = (group["status_description"].str.lower() == "unoccupied").sum()
        availability_pct = round((available / total) * 100, 2) if total else 0.0
        hourly_list.append({
            "day": str(day)[:3],
            "hour": int(hour),
            "availability": availability_pct
        })

    return JsonResponse({
        "weeklyData": weekly_list,
        "hourlyData": hourly_list
    })
