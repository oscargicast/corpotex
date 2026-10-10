from django.urls import path

from . import views

urlpatterns = [
    path("monitor/", views.MonitorView.as_view(), name="monitor"),
    path("manager/pending/", views.ManagerPendingView.as_view(), name="manager-pending"),
    path("manager/decisions/<int:pk>/", views.DecisionResolveView.as_view(), name="manager-decision"),
    path("alerts/", views.AlertListView.as_view(), name="alerts"),
    path("alerts/<int:pk>/acknowledge/", views.AlertAcknowledgeView.as_view(), name="alert-acknowledge"),
    path("me/badges/", views.BadgesView.as_view(), name="badges"),
]
