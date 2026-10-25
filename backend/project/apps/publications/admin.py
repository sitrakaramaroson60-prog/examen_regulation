from django.contrib import admin

from .models import Comment, Publication

admin.site.register(Publication)
admin.site.register(Comment)
