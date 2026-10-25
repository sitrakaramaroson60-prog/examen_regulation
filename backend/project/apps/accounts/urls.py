from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ChangePasswordView, LoginView, LogoutView, MeView, RefreshView, UserAdminViewSet

router = DefaultRouter()
router.register("users", UserAdminViewSet, basename="user-admin")

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
] + router.urls
