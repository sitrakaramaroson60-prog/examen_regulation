from rest_framework.routers import DefaultRouter

from .views import CommentViewSet

router = DefaultRouter()
router.register("", CommentViewSet, basename="comment")
urlpatterns = router.urls
