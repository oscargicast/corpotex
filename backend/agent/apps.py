from django.apps import AppConfig


class AgentConfig(AppConfig):
    """WhatsApp agent and dashboard assistant: tasks, tools and prompts (owned by the `agente`
    session; `agent/persona/` by `personalidad`). No models."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "agent"
    verbose_name = "Agente"
