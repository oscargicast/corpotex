"""The simulator's tick (ADR 0026 §5): short, re-queues itself on `periodic`. Never a long task:
the worker has 3 threads shared with the WhatsApp turns."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="fleet.tasks.simulate_tick", ignore_result=True)
def simulate_tick(vehicle_id: int, run: int) -> bool:
    from . import simulator
    from .models import Vehicle

    vehicle = Vehicle.objects.filter(pk=vehicle_id).first()
    if vehicle is None or not vehicle.sim_active or vehicle.sim_run != run:
        return False  # Stopped, or a newer run took over.
    try:
        going = simulator.step(vehicle)
    except Exception:
        logger.exception("simulate_tick: vehicle %s stopped", vehicle_id)
        Vehicle.objects.filter(pk=vehicle_id).update(sim_active=False)
        return False
    if going:
        simulate_tick.apply_async((vehicle_id, run), countdown=vehicle.sim_interval_s, queue="periodic")
    return going
