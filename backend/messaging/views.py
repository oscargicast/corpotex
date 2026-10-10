"""Simulator, conversations and the dashboard assistant (ADR 0017, 0020)."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsManager
from django.utils import timezone

from . import services
from .models import AllowedNumber, Conversation, Message, Turn


class MessageSerializer(serializers.ModelSerializer):
    media = serializers.SerializerMethodField()
    direction = serializers.CharField(read_only=True)

    class Meta:
        model = Message
        fields = ["id", "direction", "author", "text", "media", "status", "sent_at", "turn_id"]

    def get_media(self, obj) -> str | None:
        return obj.media.url if obj.media else None


class AssistantMessageSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source="sent_at", read_only=True)
    action = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ["id", "role", "text", "action", "read_at", "created_at"]

    def get_role(self, obj) -> str:
        return "assistant" if obj.author == Message.Author.AGENT else "user"

    def get_action(self, obj) -> dict | None:
        action = obj.action
        if not action or action.get("kind") != "alert":
            return action
        from manager.models import Alert

        alerts = Alert.objects.filter(id__in=action.get("alert_ids", [])).select_related("order", "purchase_order")
        by_id = {a.id: a for a in alerts}
        return {
            **action,
            "alerts": [
                {
                    "id": a.id,
                    "kind": a.kind,
                    "kind_display": a.get_kind_display(),
                    "severity": a.severity,
                    "order": {"id": a.order_id, "code": a.order.code} if a.order_id else None,
                    "purchase_order": {"id": a.purchase_order_id, "code": a.purchase_order.code} if a.purchase_order_id else None,
                }
                for a in (by_id[i] for i in action.get("alert_ids", []) if i in by_id)
            ],
        }


def _typing(conversation) -> bool:
    return conversation.turns.filter(status=Turn.Status.RUNNING).exists()


class SimulatorContactsView(APIView):
    """Active numbers with their simulator and WhatsApp conversations, never the phone."""

    permission_classes = [IsManager]

    @extend_schema(responses={200: dict})
    def get(self, request):
        rows = []
        for number in AllowedNumber.objects.filter(active=True).select_related("supplier").order_by("supplier__name", "id"):
            for conversation in number.conversations.exclude(channel="dashboard").order_by("channel"):
                last = conversation.messages.order_by("-sent_at", "-id").first()
                rows.append(
                    {
                        "allowed_number_id": number.id,
                        "name": number.name,
                        "supplier": {"id": number.supplier_id, "name": number.supplier.name} if number.supplier_id else None,
                        "channel": conversation.channel,
                        "conversation_id": conversation.id,
                        "simulated": number.simulated,
                        "last_message": {"id": last.id, "text": last.text, "direction": last.direction, "sent_at": last.sent_at} if last else None,
                    }
                )
            if number.simulated and not number.conversations.filter(channel="simulator").exists():
                rows.append(
                    {
                        "allowed_number_id": number.id,
                        "name": number.name,
                        "supplier": {"id": number.supplier_id, "name": number.supplier.name} if number.supplier_id else None,
                        "channel": "simulator",
                        "conversation_id": None,
                        "simulated": True,
                        "last_message": None,
                    }
                )
        return Response(rows)


class SimulatorMessageInSerializer(serializers.Serializer):
    allowed_number_id = serializers.IntegerField()
    text = serializers.CharField(allow_blank=True, required=False, default="")
    photo = serializers.ImageField(required=False)


class SimulatorMessagesView(APIView):
    """A team member acting as a supplier writes here; the agent answers in the same chat."""

    permission_classes = [IsManager]

    @extend_schema(request=SimulatorMessageInSerializer, responses={201: MessageSerializer})
    def post(self, request):
        data = SimulatorMessageInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        number = AllowedNumber.objects.filter(pk=data.validated_data["allowed_number_id"], active=True).first()
        if number is None:
            raise ValidationError({"allowed_number_id": "Número no permitido o inactivo."})
        conversation = services.conversation_for_number(number, Conversation.Channel.SIMULATOR)
        message = Message.objects.create(
            conversation=conversation,
            author=Message.Author.SUPPLIER,
            text=data.validated_data.get("text", ""),
            media=data.validated_data.get("photo"),
            status=Message.Status.RECEIVED,
            sent_at=timezone.now(),
        )
        services.enqueue_turn(conversation, "message")
        payload = MessageSerializer(message).data
        payload["conversation_id"] = conversation.id
        return Response(payload, status=status.HTTP_201_CREATED)


class ConversationMessagesView(APIView):
    """Read-only chat for the simulator and the purchase order detail (manager only: supplier
    messages may carry prices)."""

    permission_classes = [IsManager]

    @extend_schema(responses={200: dict})
    def get(self, request, pk: int):
        conversation = Conversation.objects.exclude(channel="dashboard").filter(pk=pk).first()
        if conversation is None:
            return Response(status=404)
        after = int(request.query_params.get("after") or 0)
        messages = conversation.messages.filter(id__gt=after).order_by("sent_at", "id")
        return Response({"typing": _typing(conversation), "messages": MessageSerializer(messages, many=True).data})


class AssistantMessageInSerializer(serializers.Serializer):
    text = serializers.CharField()
    context = serializers.DictField(required=False)


class AssistantMessagesView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request):
        conversation = services.dashboard_conversation(request.user)
        after = int(request.query_params.get("after") or 0)
        messages = conversation.messages.filter(id__gt=after).order_by("sent_at", "id")
        return Response(
            {
                "conversation_id": conversation.id,
                "typing": _typing(conversation),
                "messages": AssistantMessageSerializer(messages, many=True).data,
            }
        )

    @extend_schema(request=AssistantMessageInSerializer, responses={201: AssistantMessageSerializer})
    def post(self, request):
        data = AssistantMessageInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        conversation = services.dashboard_conversation(request.user)
        message = Message.objects.create(
            conversation=conversation,
            author=Message.Author.USER,
            text=data.validated_data["text"],
            context=data.validated_data.get("context"),
            status=Message.Status.RECEIVED,
            sent_at=timezone.now(),
        )
        services.enqueue_turn(conversation, "message")
        return Response(AssistantMessageSerializer(message).data, status=status.HTTP_201_CREATED)


class AssistantReadView(APIView):
    @extend_schema(request=None, responses={200: dict})
    def post(self, request):
        conversation = services.dashboard_conversation(request.user)
        up_to = int(request.data.get("up_to_id") or 0)
        return Response({"marked": services.mark_assistant_read(conversation, up_to)})


class AssistantResetView(APIView):
    @extend_schema(request=None, responses={200: dict})
    def post(self, request):
        conversation = services.dashboard_conversation(request.user)
        conversation.agent_session = ""
        conversation.pending_action = None
        conversation.save(update_fields=["agent_session", "pending_action", "updated_at"])
        return Response({"detail": "ok"})
