from django.urls import path

from . import views

urlpatterns = [
    path("dispatches/", views.DispatchListView.as_view(), name="dispatches"),
    path("dispatches/<int:order_id>/", views.DispatchDetailView.as_view(), name="dispatch-detail"),
    path("vehicles/", views.VehicleListView.as_view(), name="vehicles"),
    path("vehicles/live/", views.VehicleLiveView.as_view(), name="vehicles-live"),
    path("vehicles/stream/", views.VehicleStreamView.as_view(), name="vehicles-stream"),
    path("vehicles/<int:pk>/positions/", views.VehiclePositionsView.as_view(), name="vehicle-positions"),
    path("vehicles/<int:pk>/simulate/", views.VehicleSimulateView.as_view(), name="vehicle-simulate"),
    path("routes/plan-day/", views.PlanDayView.as_view(), name="route-plan-day"),
    path("routes/<int:pk>/start/", views.RouteStartView.as_view(), name="route-start"),
    path("routes/<int:pk>/complete/", views.RouteCompleteView.as_view(), name="route-complete"),
    path("routes/<int:pk>/stops/<int:stop_id>/deliver/", views.StopDeliverView.as_view(), name="route-stop-deliver"),
]
