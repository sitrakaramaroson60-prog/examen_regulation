from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import City, Organization, Region
from .serializers import CitySerializer, OrganizationSerializer, RegionSerializer


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    """Liste des organisations (utile aux filtres du frontend). Lecture seule."""

    queryset = Organization.objects.filter(is_active=True)
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class RegionViewSet(viewsets.ReadOnlyModelViewSet):
    """Référentiel public des régions (avec leurs villes)."""

    queryset = Region.objects.filter(is_active=True).prefetch_related("cities")
    serializer_class = RegionSerializer
    permission_classes = [AllowAny]
    pagination_class = None


class CityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = City.objects.filter(is_active=True, region__is_active=True).select_related("region")
    serializer_class = CitySerializer
    permission_classes = [AllowAny]
    pagination_class = None
    filterset_fields = ["region"]
