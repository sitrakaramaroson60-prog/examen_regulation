from rest_framework.routers import DefaultRouter

from .views import CityViewSet, OrganizationViewSet, RegionViewSet

router = DefaultRouter()
router.register("regions", RegionViewSet, basename="region")
router.register("cities", CityViewSet, basename="city")
router.register("", OrganizationViewSet, basename="organization")
urlpatterns = router.urls
