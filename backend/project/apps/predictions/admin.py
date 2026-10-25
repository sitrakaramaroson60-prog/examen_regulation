from django.contrib import admin

from .models import PredictionModel, PredictionRun

admin.site.register(PredictionModel)
admin.site.register(PredictionRun)
