"""ADR 0030: the manager pauses the agent for every supplier at once (here) or for one
(`PATCH /api/suppliers/<id>/ {agent_paused}`). The dashboard assistants never pause."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Config
from .permissions import IsManager


class AgentSettingsSerializer(serializers.Serializer):
    paused = serializers.BooleanField(help_text="The agent writes to no supplier; incoming messages are still kept.")
    paused_suppliers = serializers.IntegerField(read_only=True, help_text="Suppliers paused one by one.")


class AgentSettingsInSerializer(serializers.Serializer):
    paused = serializers.BooleanField()


def agent_settings() -> dict:
    from suppliers.models import Supplier

    return {"paused": Config.load().agent_paused, "paused_suppliers": Supplier.objects.filter(agent_paused=True).count()}


class AgentSettingsView(APIView):
    """`GET/PATCH /api/settings/agent/` (manager only). Resuming queues the first contact of the
    purchase orders approved during the pause; the tick resumes the follow-ups."""

    permission_classes = [IsManager]

    @extend_schema(responses={200: AgentSettingsSerializer})
    def get(self, request):
        return Response(AgentSettingsSerializer(agent_settings()).data)

    @extend_schema(request=AgentSettingsInSerializer, responses={200: AgentSettingsSerializer})
    def patch(self, request):
        from messaging.services import resume_agent

        data = AgentSettingsInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        config = Config.load()
        was_paused, config.agent_paused = config.agent_paused, data.validated_data["paused"]
        config.save(update_fields=["agent_paused", "updated_at"])
        if was_paused and not config.agent_paused:
            resume_agent()
        return Response(AgentSettingsSerializer(agent_settings()).data)
