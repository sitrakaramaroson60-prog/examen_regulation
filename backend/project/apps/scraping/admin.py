from django.contrib import admin

from .models import ScrapingJob, ScrapingSource

admin.site.register(ScrapingSource)
admin.site.register(ScrapingJob)
