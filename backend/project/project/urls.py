from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("organizations/", include("apps.organizations.urls")),
    path("publications/", include("apps.publications.urls")),
    path("comments/", include("apps.publications.comment_urls")),
    path("surveys/", include("apps.surveys.urls")),
    path("datasets/", include("apps.datasets.urls")),
    path("submissions/", include("apps.datasets.submission_urls")),
    path("scraping/", include("apps.scraping.urls")),
    path("qos/", include("apps.qos.urls")),
    path("predictions/", include("apps.predictions.urls")),
    path("regulation/", include("apps.regulation.urls")),
    path("complaints/", include("apps.complaints.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("audit/", include("apps.audit.urls")),
    path("realtime/", include("apps.realtime.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
