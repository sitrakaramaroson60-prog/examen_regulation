from django.contrib import admin

from .models import QoSMeasurement, QoSThreshold

admin.site.register(QoSMeasurement)
admin.site.register(QoSThreshold)
