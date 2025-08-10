from django.db import models

class OnStreetParkingBaySensor(models.Model):
    lastupdated = models.DateTimeField()
    status_timestamp = models.DateTimeField()
    zone_number = models.IntegerField(null=True, blank=True)
    status_description = models.CharField(max_length=50)
    kerbsideid = models.IntegerField()
    location = models.CharField(max_length=255)
    day = models.CharField(max_length=20)
    time = models.CharField(max_length=20)
    timestamp = models.TimeField()

    class Meta:
        db_table = 'onstreet_parking_bay_sensors'
        managed = False  # if the table is managed by another system, set to False




class ParkingZoneSegment(models.Model):
    parking_zone = models.IntegerField(db_column="ParkingZone")  
    on_street = models.CharField(max_length=255, db_column="OnStreet")  
    street_from = models.CharField(max_length=255, db_column="StreetFrom")  
    street_to = models.CharField(max_length=255, db_column="StreetTo")  
    segment_id = models.IntegerField(db_column="Segment_ID", primary_key=True)  

    class Meta:
        db_table = "parking_zone_segments"
        managed = False  # if the table is managed by another system, set to False
        verbose_name = "Parking Zone Segment"
        verbose_name_plural = "Parking Zone Segments"