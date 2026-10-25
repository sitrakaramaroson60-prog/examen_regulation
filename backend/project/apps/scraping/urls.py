from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import JobViewSet, RecordViewSet, SourceViewSet, StatusView

router = DefaultRouter()
router.register("sources", SourceViewSet, basename="scraping-source")
router.register("jobs", JobViewSet, basename="scraping-job")
router.register("records", RecordViewSet, basename="scraping-record")
urlpatterns = [path("status/", StatusView.as_view(), name="scraping-status")] + router.urls
