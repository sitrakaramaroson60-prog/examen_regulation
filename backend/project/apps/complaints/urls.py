from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ComplaintViewSet, PublicComplaintView, PublicTrackView

router = DefaultRouter()
router.register("", ComplaintViewSet, basename="complaint")
urlpatterns = [
    path("public/", PublicComplaintView.as_view(), name="complaint-public"),
    path("public/track/", PublicTrackView.as_view(), name="complaint-track"),
] + router.urls
