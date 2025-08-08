from django.shortcuts import render

# Create your views here.
def home(request):
    return render(request, 'parkspot_home.html')

def predictions(request):
    return render(request, 'predictions.html')

def analytics(request):
    return render(request, 'historical_analytics.html')

def contact(request):
    return render(request, 'contact.html')

def live_parking(request):
    # Example data for live parking spots
    parking_spots = [
        {
            "name": "Collins Street Precinct",
            "address": "Collins St between King & William",
            "lat": -37.817123,
            "lng": 144.955876,
            "available": 45,
            "total": 120,
            "distance": "0.2km",
            "prediction": "decreasing",
            "walkTime": "3 min",
            "price": "$8.50/hr"
        },
        {
            "name": "Bourke Street Mall",
            "address": "Bourke St Mall Car Park",
            "lat": -37.814174,
            "lng": 144.965549,
            "available": 78,
            "total": 200,
            "distance": "0.4km",
            "prediction": "stable",
            "walkTime": "5 min",
            "price": "$9.00/hr"
        },
        {
            "name": "Flinders Street Station",
            "address": "Flinders St Underground",
            "lat": -37.818271,
            "lng": 144.967061,
            "available": 12,
            "total": 85,
            "distance": "0.6km",
            "prediction": "increasing",
            "walkTime": "7 min",
            "price": "$7.50/hr"
        },
        {
            "name": "Queen Victoria Market",
            "address": "QV Car Park",
            "lat": -37.807783,
            "lng": 144.956736,
            "available": 156,
            "total": 180,
            "distance": "0.8km",
            "prediction": "stable",
            "walkTime": "10 min",
            "price": "$6.00/hr"
        },
        {
            "name": "Southern Cross Station",
            "address": "Spencer St Car Park",
            "lat": -37.818249,
            "lng": 144.952708,
            "available": 9,
            "total": 55,
            "distance": "1.1km",
            "prediction": "decreasing",
            "walkTime": "13 min",
            "price": "$8.80/hr"
        },
        {
            "name": "Melbourne Central",
            "address": "La Trobe St Car Park",
            "lat": -37.810634,
            "lng": 144.963307,
            "available": 34,
            "total": 90,
            "distance": "0.9km",
            "prediction": "increasing",
            "walkTime": "8 min",
            "price": "$7.00/hr"
        },
        {
            "name": "Docklands Harbour",
            "address": "Docklands Waterfront Car Park",
            "lat": -37.816218,
            "lng": 144.942964,
            "available": 111,
            "total": 130,
            "distance": "1.5km",
            "prediction": "stable",
            "walkTime": "15 min",
            "price": "$5.50/hr"
        },
        {
            "name": "RMIT University",
            "address": "Swanston St Car Park",
            "lat": -37.807692,
            "lng": 144.965324,
            "available": 21,
            "total": 60,
            "distance": "0.5km",
            "prediction": "decreasing",
            "walkTime": "6 min",
            "price": "$7.90/hr"
        },
        {
            "name": "State Library",
            "address": "Russell St",
            "lat": -37.809755,
            "lng": 144.965502,
            "available": 56,
            "total": 70,
            "distance": "0.7km",
            "prediction": "stable",
            "walkTime": "9 min",
            "price": "$6.20/hr"
        },
        {
            "name": "Emporium Melbourne",
            "address": "Lonsdale St Car Park",
            "lat": -37.812251,
            "lng": 144.963982,
            "available": 41,
            "total": 85,
            "distance": "0.3km",
            "prediction": "increasing",
            "walkTime": "3 min",
            "price": "$9.20/hr"
        },
        {
            "name": "Southbank Promenade",
            "address": "Southbank Blvd Car Park",
            "lat": -37.821095,
            "lng": 144.964584,
            "available": 64,
            "total": 105,
            "distance": "1.2km",
            "prediction": "stable",
            "walkTime": "14 min",
            "price": "$8.30/hr"
        },
        {
            "name": "Carlton Gardens",
            "address": "Exhibition St",
            "lat": -37.805518,
            "lng": 144.971798,
            "available": 13,
            "total": 60,
            "distance": "1.1km",
            "prediction": "decreasing",
            "walkTime": "12 min",
            "price": "$5.80/hr"
        },
        {
            "name": "Flagstaff Gardens",
            "address": "William St Car Park",
            "lat": -37.810237,
            "lng": 144.954648,
            "available": 85,
            "total": 120,
            "distance": "1.0km",
            "prediction": "stable",
            "walkTime": "11 min",
            "price": "$6.50/hr"
        }
    ]

    
    # 根據剩餘比例分顏色
    for spot in parking_spots:
        percent = spot["available"] / spot["total"] if spot["total"] else 0
        if percent < 0.3:
            badge = "red"
        elif percent < 0.7:
            badge = "yellow"
        else:
            badge = "green"
        spot["badge"] = badge   # 新增 badge 欄位進 dict
    return render(request, "live_parking.html", {"parking_spots": parking_spots})