from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from messaging.webhook import evolution_webhook

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/", include("core.urls")),
    path("api/", include("suppliers.urls")),
    path("api/", include("operations.urls")),
    path("api/", include("messaging.urls")),
    path("api/", include("manager.urls")),
    path("api/", include("fleet.urls")),
    path("webhooks/evolution/<str:secret>/", evolution_webhook, name="evolution-webhook"),
]

# Media is served by Django in development and behind the tunnel (ADR 0006, 0023).
# Django serves media behind the tunnel in every mode (ADR 0006/0023); `static()` only works with DEBUG.
urlpatterns += [re_path(r"^media/(?P<path>.*)$", lambda request, path: serve(request, path, document_root=settings.MEDIA_ROOT))]
