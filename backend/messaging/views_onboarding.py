"""Step 1 of the onboarding: link WhatsApp and configure the instance (ADR 0011, B4.4).

Gerente only. Owned by the `orquestador` session; the pure logic lives in
`messaging.whatsapp_onboarding`. The views never create, disconnect or delete an
instance. `Config.onboarding["whatsapp"]["done_at"]` records the first time the
step was seen complete (linked and webhook pointing at us, or done offline)."""

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Config
from core.permissions import IsManager

from . import whatsapp_onboarding
from .evolution import EvolutionClient, EvolutionError

STEP = "whatsapp"


class WebhookSummarySerializer(serializers.Serializer):
    url = serializers.CharField(help_text="Secret masked as ****.")
    events = serializers.ListField(child=serializers.CharField())
    base64 = serializers.BooleanField()


class WhatsAppOnboardingSerializer(serializers.Serializer):
    state = serializers.CharField()
    webhook = WebhookSummarySerializer(allow_null=True)
    settings = serializers.DictField(allow_null=True)
    offline = serializers.BooleanField()
    done_at = serializers.CharField(allow_null=True)


class WhatsAppQrSerializer(serializers.Serializer):
    qr_base64 = serializers.CharField(allow_null=True, help_text="data:image/png;base64,…")


class OnboardingErrorSerializer(serializers.Serializer):
    error_code = serializers.CharField()
    detail = serializers.CharField()


def _client() -> EvolutionClient:
    return EvolutionClient.from_settings()


def _webhook_url() -> str | None:
    try:
        return whatsapp_onboarding.webhook_url_from_env(
            {
                "EVOLUTION_WEBHOOK_SECRET": settings.EVOLUTION_WEBHOOK_SECRET,
                "PUBLIC_BASE_URL": getattr(settings, "PUBLIC_BASE_URL", ""),
            }
        )
    except ValueError:
        return None


def _mark_done(config: Config) -> str:
    step = dict(config.onboarding.get(STEP) or {})
    if not step.get("done_at"):
        step["done_at"] = timezone.now().isoformat()
        config.onboarding = {**config.onboarding, STEP: step}
        config.save(update_fields=["onboarding", "updated_at"])
    return step["done_at"]


def _payload(status: dict) -> dict:
    config = Config.load()
    done_at = (config.onboarding.get(STEP) or {}).get("done_at")
    if status.pop("done", False):
        done_at = _mark_done(config)
    return {**status, "done_at": done_at}


def _error(code: str, detail: str, status: int) -> Response:
    return Response({"error_code": code, "detail": detail}, status=status)


def _evolution_error(exc: EvolutionError) -> Response:
    return _error("evolution_unavailable", f"No se pudo hablar con Evolution: {exc}", 502)


def _secret_missing() -> Response:
    return _error("webhook_secret_missing", "Falta EVOLUTION_WEBHOOK_SECRET en el .env.", 400)


class WhatsAppOnboardingView(APIView):
    permission_classes = (IsManager,)

    @extend_schema(responses={200: WhatsAppOnboardingSerializer, 502: OnboardingErrorSerializer})
    def get(self, request):
        client = _client()
        webhook_url = _webhook_url()
        if client.has_access_token and webhook_url is None:
            return _secret_missing()
        try:
            status = whatsapp_onboarding.onboarding_status(
                client, webhook_url=webhook_url or "", has_access_token=client.has_access_token
            )
        except EvolutionError as exc:
            return _evolution_error(exc)
        return Response(WhatsAppOnboardingSerializer(_payload(status)).data)


class WhatsAppQrView(APIView):
    permission_classes = (IsManager,)

    @extend_schema(
        request=None, responses={200: WhatsAppQrSerializer, 502: OnboardingErrorSerializer}
    )
    def post(self, request):
        try:
            qr = whatsapp_onboarding.qr(_client())
        except EvolutionError as exc:
            return _evolution_error(exc)
        return Response({"qr_base64": qr})


class WhatsAppWebhookView(APIView):
    permission_classes = (IsManager,)

    @extend_schema(
        request=None,
        responses={200: WhatsAppOnboardingSerializer, 502: OnboardingErrorSerializer},
    )
    def post(self, request):
        webhook_url = _webhook_url()
        if webhook_url is None:
            return _secret_missing()
        try:
            status = whatsapp_onboarding.configure(_client(), webhook_url=webhook_url)
        except EvolutionError as exc:
            return _evolution_error(exc)
        return Response(WhatsAppOnboardingSerializer(_payload(status)).data)
