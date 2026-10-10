"""`python manage.py seed_demo`: wipes and reloads the demo data from `backend/seed/data/`
(ADR 0021). Idempotent; never touches users, tokens, the WhatsApp onboarding state nor the
approved style unless `--reset-style` is passed. Aborts without partial data on any error."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from seed.loader import Loader, SeedError


class Command(BaseCommand):
    help = "Carga la data de la demo desde backend/seed/data (borra y recrea; el estilo se conserva)."

    def add_arguments(self, parser):
        parser.add_argument("--reset-style", action="store_true", help="Recrea las StyleVersion y User.style_md desde los JSON.")
        parser.add_argument("--data-dir", help="Otra carpeta de fixtures (por defecto backend/seed/data).")

    def handle(self, *args, **options):
        from pathlib import Path

        loader = Loader(data_dir=Path(options["data_dir"]) if options.get("data_dir") else None or Loader().data_dir, out=self.stdout.write)
        try:
            with transaction.atomic():
                loader.load_users()
                loader.wipe()
                loader.load_config()
                loader.load_catalogue()
                loader.load_suppliers()
                loader.load_orders()
                loader.load_purchase_orders()
                loader.load_decisions()
                loader.load_alerts()
                loader.load_conversations()
                loader.load_style(reset=options["reset_style"])
                loader.load_status_history()
                loader.finish()
        except SeedError as exc:
            raise CommandError(str(exc)) from exc
        from operations.models import Order, PurchaseOrder
        from suppliers.models import Supplier

        self.stdout.write(
            self.style.SUCCESS(
                f"seed_demo: {Supplier.objects.count()} proveedores, {Order.objects.count()} órdenes, "
                f"{PurchaseOrder.objects.count()} pedidos. T = {loader.t:%d/%m %H:%M}."
            )
        )
