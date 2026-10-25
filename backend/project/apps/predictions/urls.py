from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import ForecastView, PredictionModelViewSet, PredictionRunViewSet, RiskTypesView, TrainingSetView

router = DefaultRouter()
router.register("models", PredictionModelViewSet, basename="prediction-model")
router.register("runs", PredictionRunViewSet, basename="prediction-run")
urlpatterns = [
    path("training-sets/build/", TrainingSetView.as_view(), name="training-set-build"),
    path("forecast/", ForecastView.as_view(), name="forecast"),
    path("risk-types/", RiskTypesView.as_view(), name="risk-types"),
] + router.urls
