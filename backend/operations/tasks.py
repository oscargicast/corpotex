"""Background classification (ADR 0028, M3): an order that comes in with items without a product
classifies itself, no human confirmation. Short task on `periodic`."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)
RETRY_SECONDS = 60


@shared_task(name="operations.tasks.auto_classify", ignore_result=True)
def auto_classify(order_id: int, attempt: int = 1) -> dict:
    """Classifies and applies; a failed line retries once after 60 s, then the order keeps
    `needs_classification` and production gets a `classification_failed` alert."""
    from manager.services import open_alert

    from .classify import auto_classify_order
    from .models import Order

    order = Order.objects.filter(pk=order_id).exclude(status__in=(Order.Status.CANCELLED, Order.Status.DELIVERED)).select_related("customer", "brand").first()
    if order is None:
        return {"done": 0, "failed": 0}
    done, failed = auto_classify_order(order)
    if failed and attempt < 2:
        auto_classify.apply_async((order_id, attempt + 1), countdown=RETRY_SECONDS, queue="periodic")
    elif failed:
        first = (failed[0].description or "").strip()[:60]
        more = f" (y {len(failed) - 1} más)" if len(failed) > 1 else ""
        open_alert(
            "classification_failed",
            order=order,
            text=f"No se pudo reconocer '{first}' en {order.code}{more}",
            detail={"order_code": order.code, "items": [{"id": i.id, "description": i.description} for i in failed]},
        )
    return {"done": done, "failed": len(failed)}
