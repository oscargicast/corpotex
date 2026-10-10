from django.apps import AppConfig


class SeedConfig(AppConfig):
    """`seed_demo` command, demo fixtures and images (ADR 0021). No models."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "seed"
    verbose_name = "Seed"
