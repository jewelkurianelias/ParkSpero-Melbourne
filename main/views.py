from django.shortcuts import render
from django.http import JsonResponse
import json
from django.views.decorators.http import require_GET
from .services import home_service, predictions_service, analytics_service, live_parking_service


# Create your views here.
def home(request):
    return render(request, 'parkspot_home.html')

def predictions(request):
    return render(request, 'predictions.html')

#def analytics(request):
    #return render(request, 'historical_analytics.html')

def analytics(request):
    chart_data = analytics_service.parking_chart_data(request)
    chart_data_dict = json.loads(chart_data.content)

    return render(request, 'historical_analytics.html', {
        "weeklyData": chart_data_dict["weeklyData"],
        "hourlyData": chart_data_dict["hourlyData"],
    })

def contact(request):
    return render(request, 'contact.html')

def live_parking(request):
    if not live_parking_service.get_live_parking_data():  # If there is no data in the cache
        live_parking_service.fetch_and_cache_parking()
    parking_spots = live_parking_service.get_live_parking_data()
    return render(request, "live_parking.html", {"parking_spots": parking_spots})

def live_parking_api(request):
    live_parking_service.fetch_and_cache_parking()  # Refresh to update
    return JsonResponse(live_parking_service.get_live_parking_data(), safe=False)

@require_GET
def predictions_api(request):
    payload = predictions_service.predict_now()  # already cached ~60s in the service
    return JsonResponse(payload, safe=False)