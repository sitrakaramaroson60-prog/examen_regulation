from django.urls import path

from .views import EventsView

urlpatterns = [path("events/", EventsView.as_view(), name="realtime-events")]
