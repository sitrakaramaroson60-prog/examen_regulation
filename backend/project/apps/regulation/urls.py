from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AlertViewSet,
    CaseViewSet,
    CheckViewSet,
    CorrectiveActionViewSet,
    DecisionViewSet,
    ObligationViewSet,
    OperatorFilesIndexView,
    OperatorFileView,
    OverviewView,
)

router = DefaultRouter()
router.register("cases", CaseViewSet, basename="regulatory-case")
router.register("decisions", DecisionViewSet, basename="regulatory-decision")
router.register("corrective-actions", CorrectiveActionViewSet, basename="corrective-action")
router.register("obligations", ObligationViewSet, basename="obligation")
router.register("alerts", AlertViewSet, basename="compliance-alert")
router.register("checks", CheckViewSet, basename="followup-check")
urlpatterns = [
    path("overview/", OverviewView.as_view(), name="regulation-overview"),
    path("operator-files/", OperatorFilesIndexView.as_view(), name="operator-files"),
    path("operator-files/<str:code>/", OperatorFileView.as_view(), name="operator-file"),
] + router.urls
