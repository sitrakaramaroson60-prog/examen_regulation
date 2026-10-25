from django.contrib import admin

from .models import City, Organization, Region

admin.site.register(Organization)
admin.site.register(Region)
admin.site.register(City)
