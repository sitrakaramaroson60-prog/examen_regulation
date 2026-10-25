from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import OverviewView, PublicationViewSet, PublicPublicationViewSet

router = DefaultRouter()
router.register("public", PublicPublicationViewSet, basename="public-publication")
router.register("", PublicationViewSet, basename="publication")
urlpatterns = [path("overview/", OverviewView.as_view(), name="publications-overview")] + router.urls
