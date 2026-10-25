from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BarometerSettingView, MeasurementViewSet, PublicSummaryView, ThresholdViewSet

router = DefaultRouter()
router.register("thresholds", ThresholdViewSet, basename="qos-threshold")
router.register("measurements", MeasurementViewSet, basename="qos-measurement")
urlpatterns = [
    path("public/", PublicSummaryView.as_view(), name="qos-public"),
    path("public/settings/", BarometerSettingView.as_view(), name="qos-public-settings"),
] + router.urls
