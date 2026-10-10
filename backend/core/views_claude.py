"""Claude account connection from the dashboard (ADR 0022, planning B4.3). Gerente only.

Owned by the `orquestador` session. Errors from `claude_auth` come back as
`{error_code, detail}` with the status the error carries (400 for the user's
mistakes, 502 when claude.ai or Anthropic could not be reached)."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from . import claude_account
from .claude_auth import ClaudeAuthError
from .permissions import IsManager


class ClaudeStatusSerializer(serializers.Serializer):
    connected = serializers.BooleanField()
    method = serializers.ChoiceField(choices=["oauth", "api_key", "none"])
    subscription_type = serializers.CharField(allow_null=True)
    expires_at = serializers.IntegerField(allow_null=True, help_text="Epoch milliseconds.")
    refresh_token_expires_at = serializers.IntegerField(allow_null=True)
    expired = serializers.BooleanField()
    connected_at = serializers.DateTimeField(allow_null=True)
    last_error = serializers.CharField(allow_null=True)
    last_error_at = serializers.DateTimeField(allow_null=True)


class ClaudeStartSerializer(serializers.Serializer):
    url = serializers.URLField()
    state = serializers.CharField()


class ClaudeExchangeSerializer(serializers.Serializer):
    code = serializers.CharField(
        trim_whitespace=False, help_text="`<code>#<state>` as shown by Anthropic."
    )


class ClaudeApiKeySerializer(serializers.Serializer):
    api_key = serializers.CharField(trim_whitespace=False)


class ClaudeErrorSerializer(serializers.Serializer):
    error_code = serializers.CharField()
    detail = serializers.CharField()


def _status_response() -> Response:
    return Response(ClaudeStatusSerializer(claude_account.status()).data)


def _error(exc: ClaudeAuthError) -> Response:
    return Response({"error_code": exc.code, "detail": exc.message}, status=exc.status)


class ClaudeStatusView(APIView):
    permission_classes = (IsManager,)

    @extend_schema(responses=ClaudeStatusSerializer)
    def get(self, request):
        return _status_response()


class ClaudeStartView(APIView):
    permission_classes = (IsManager,)

    @extend_schema(request=None, responses=ClaudeStartSerializer)
    def post(self, request):
        return Response(ClaudeStartSerializer(claude_account.start()).data)


class ClaudeExchangeView(APIView):
    permission_classes = (IsManager,)

    @extend_schema(
        request=ClaudeExchangeSerializer,
        responses={200: ClaudeStatusSerializer, 400: ClaudeErrorSerializer},
    )
    def post(self, request):
        data = ClaudeExchangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            claude_account.connect_with_code(data.validated_data["code"])
        except ClaudeAuthError as exc:
            return _error(exc)
        return _status_response()


class ClaudeSetKeyView(APIView):
    permission_classes = (IsManager,)

    @extend_schema(
        request=ClaudeApiKeySerializer,
        responses={200: ClaudeStatusSerializer, 400: ClaudeErrorSerializer},
    )
    def post(self, request):
        data = ClaudeApiKeySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            claude_account.connect_with_api_key(data.validated_data["api_key"])
        except ClaudeAuthError as exc:
            return _error(exc)
        return _status_response()


class ClaudeDisconnectView(APIView):
    permission_classes = (IsManager,)

    @extend_schema(
        request=None, responses={200: ClaudeStatusSerializer, 400: ClaudeErrorSerializer}
    )
    def post(self, request):
        try:
            claude_account.disconnect()
        except ClaudeAuthError as exc:
            return _error(exc)
        return _status_response()
