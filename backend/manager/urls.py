from django.urls import path

from . import views

urlpatterns = [
    path("monitor/", views.MonitorView.as_view(), name="monitor"),
]
