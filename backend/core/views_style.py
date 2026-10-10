"""Style onboarding (`/api/onboarding/style/`) and version history (`/api/style/`), Gerente only.

Contract in ADR 0011 and 0019; the logic lives in `core.onboarding` and `core.style`. The
serializers here validate input and document the responses in the OpenAPI schema.
"""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import onboarding
from .models import OnboardingStyle, StyleVersion
from .permissions import IsManager
from .serializers import StyleVersionDetailSerializer, StyleVersionSerializer
from .style import StyleInvalid, approve_style, restore_style_version, style_owner

BUSY = {"detail": "Hay una extracción en curso."}
SUPPLIER_STATUSES = (
    "pending",
    "reading",
    "analyzing",
    "done",
    "no_phone",
    "no_chat",
    "not_allowed",
    "error",
)


class StyleSupplierProgressSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=SUPPLIER_STATUSES)
    messages_read = serializers.IntegerField(allow_null=True)
    error = serializers.CharField(allow_blank=True)


class StyleNotesSerializer(serializers.Serializer):
    supplier_id = serializers.IntegerField()
    supplier_name = serializers.CharField(read_only=True)
    notes = serializers.CharField(allow_blank=True)


class OnboardingStyleSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OnboardingStyle.Status.choices)
    status_display = serializers.CharField()
    error = serializers.CharField(allow_blank=True)
    since = serializers.DateField(allow_null=True)
    step = serializers.ChoiceField(choices=OnboardingStyle.Step.choices, allow_null=True)
    suppliers = StyleSupplierProgressSerializer(many=True)
    style_md = serializers.CharField(allow_blank=True)
    notes = StyleNotesSerializer(many=True)
    approved_at = serializers.DateTimeField(allow_null=True)


class StyleDraftSerializer(serializers.Serializer):
    style_md = serializers.CharField(allow_blank=True, trim_whitespace=False)
    notes = StyleNotesSerializer(many=True, required=False, default=list)


class StyleExtractSerializer(serializers.Serializer):
    since = serializers.DateField()
    supplier_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class StyleImportTxtSerializer(serializers.Serializer):
    file = serializers.FileField()
    manager_author = serializers.CharField()
    since = serializers.DateField()
    supplier_id = serializers.IntegerField(required=False, allow_null=True)


class StyleErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()
    errors = serializers.ListField(child=serializers.CharField(), required=False)


STATE = {200: OnboardingStyleSerializer, 400: StyleErrorSerializer, 409: StyleErrorSerializer}
ACCEPTED = {202: OnboardingStyleSerializer, 400: StyleErrorSerializer, 409: StyleErrorSerializer}


class StyleView(APIView):
    permission_classes = (IsManager,)

    def handle_exception(self, exc):
        if isinstance(exc, onboarding.StyleBusy):
            return Response(BUSY, status=status.HTTP_409_CONFLICT)
        if isinstance(exc, onboarding.StyleInputError):
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(exc, StyleInvalid):
            return Response(
                {"detail": "El estilo no pasa la validación.", "errors": exc.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().handle_exception(exc)

    def state(self, code=status.HTTP_200_OK):
        return Response(onboarding.onboarding_state(), status=code)

    def valid(self, serializer_class, request) -> dict:
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class OnboardingStyleView(StyleView):
    @extend_schema(
        operation_id="onboarding_style_retrieve", responses={200: OnboardingStyleSerializer}
    )
    def get(self, request):
        return self.state()

    @extend_schema(
        operation_id="onboarding_style_update", request=StyleDraftSerializer, responses=STATE
    )
    def put(self, request):
        data = self.valid(StyleDraftSerializer, request)
        onboarding.save_draft(style_md=data["style_md"], notes=data["notes"], actor=request.user)
        return self.state()


class StyleExtractView(StyleView):
    @extend_schema(
        operation_id="onboarding_style_extract", request=StyleExtractSerializer, responses=ACCEPTED
    )
    def post(self, request):
        data = self.valid(StyleExtractSerializer, request)
        onboarding.start_extraction(
            since=data["since"], supplier_ids=data.get("supplier_ids") or None, actor=request.user
        )
        return self.state(status.HTTP_202_ACCEPTED)


class StyleImportTxtView(StyleView):
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    @extend_schema(
        operation_id="onboarding_style_import_txt",
        request={"multipart/form-data": StyleImportTxtSerializer},
        responses=ACCEPTED,
    )
    def post(self, request):
        data = self.valid(StyleImportTxtSerializer, request)
        onboarding.import_txt(
            content=data["file"].read().decode("utf-8", errors="replace"),
            manager_author=data["manager_author"].strip(),
            since=data["since"],
            supplier_id=data.get("supplier_id"),
            actor=request.user,
        )
        return self.state(status.HTTP_202_ACCEPTED)


class StyleTemplateView(StyleView):
    @extend_schema(operation_id="onboarding_style_template", request=None, responses=STATE)
    def post(self, request):
        onboarding.load_template_draft(actor=request.user)
        return self.state()


class StyleApproveView(StyleView):
    @extend_schema(operation_id="onboarding_style_approve", request=None, responses=STATE)
    def post(self, request):
        approve_style(actor=request.user)
        return self.state()


class StyleVersionListView(StyleView):
    @extend_schema(operation_id="style_versions_list", responses=StyleVersionSerializer(many=True))
    def get(self, request):
        owner = style_owner(request.user)
        versions = StyleVersion.objects.filter(user=owner)
        return Response(StyleVersionSerializer(versions, many=True).data)


class StyleVersionDetailView(StyleView):
    @extend_schema(operation_id="style_versions_retrieve", responses=StyleVersionDetailSerializer)
    def get(self, request, pk):
        version = get_object_or_404(StyleVersion, pk=pk)
        return Response(StyleVersionDetailSerializer(version).data)


class StyleVersionRestoreView(StyleView):
    @extend_schema(
        operation_id="style_versions_restore",
        request=None,
        responses={201: StyleVersionDetailSerializer},
    )
    def post(self, request, pk):
        version = get_object_or_404(StyleVersion, pk=pk)
        restored = restore_style_version(version, actor=request.user)
        return Response(StyleVersionDetailSerializer(restored).data, status=status.HTTP_201_CREATED)


class StyleRefreshView(StyleView):
    @extend_schema(
        operation_id="style_refresh", request=None, responses={202: StyleErrorSerializer}
    )
    def post(self, request):
        from .tasks_style import refresh_style

        refresh_style.delay()
        return Response({"detail": "Refresco encolado."}, status=status.HTTP_202_ACCEPTED)
