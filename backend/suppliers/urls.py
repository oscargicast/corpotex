from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("suppliers", views.SupplierViewSet, basename="supplier")

urlpatterns = router.urls
