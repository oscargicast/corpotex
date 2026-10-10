from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import clock
from .models import Config
from .permissions import IsManager
from .serializers import (
    ClockPatchSerializer,
    ClockSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    UserSerializer,
)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(request=LoginSerializer, responses=LoginResponseSerializer)
    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = authenticate(request, **data.validated_data)
        if user is None:
            return Response({"detail": "Usuario o contraseña incorrectos."}, status=400)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})


class LogoutView(APIView):
    """Does not revoke the token: in the demo the same user has two windows open, and a
    revocation would log the other one out. The client just forgets the token."""

    @extend_schema(request=None, responses={200: None})
    def post(self, request):
        return Response({"detail": "ok"}, status=status.HTTP_200_OK)


class MeView(APIView):
    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


def _clock_payload(config: Config) -> dict:
    return {"now": clock.now(config), "factor": config.clock_factor, "paused": config.clock_paused}


class ClockView(APIView):
    @extend_schema(responses=ClockSerializer)
    def get(self, request):
        return Response(ClockSerializer(_clock_payload(Config.load())).data)

    @extend_schema(request=ClockPatchSerializer, responses=ClockSerializer)
    def patch(self, request):
        self.permission_classes = [IsManager]
        self.check_permissions(request)
        data = ClockPatchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        config = clock.set_clock(actor=request.user, **data.validated_data)
        return Response(ClockSerializer(_clock_payload(config)).data)
