from rest_framework.routers import DefaultRouter

from .views import DatasetViewSet, VersionViewSet

router = DefaultRouter()
router.register("versions", VersionViewSet, basename="dataset-version")
router.register("", DatasetViewSet, basename="dataset")
urlpatterns = router.urls
