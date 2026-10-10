"""Style onboarding (`/api/onboarding/style/`) and version history (`/api/style/`), Gerente only.

Contract in ADR 0011 and 0019; the logic lives in `core.onboarding` and `core.style`.
"""

from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import onboarding
from .models import StyleVersion
from .permissions import IsManager
from .serializers import StyleVersionDetailSerializer, StyleVersionSerializer
from .style import StyleInvalid, approve_style, restore_style_version, style_owner

BUSY = {"detail": "Hay una extracción en curso."}


def _since(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


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


class OnboardingStyleView(StyleView):
    def get(self, request):
        return self.state()

    def put(self, request):
        notes = request.data.get("notes") or []
        if not isinstance(notes, list):
            raise onboarding.StyleInputError("notes debe ser una lista de {supplier_id, notes}.")
        onboarding.save_draft(
            style_md=str(request.data.get("style_md") or ""), notes=notes, actor=request.user
        )
        return self.state()


class StyleExtractView(StyleView):
    def post(self, request):
        since = _since(request.data.get("since"))
        if since is None:
            raise onboarding.StyleInputError("Falta la fecha desde (since, AAAA-MM-DD).")
        onboarding.start_extraction(
            since=since, supplier_ids=request.data.get("supplier_ids") or None, actor=request.user
        )
        return self.state(status.HTTP_202_ACCEPTED)


class StyleImportTxtView(StyleView):
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def post(self, request):
        upload = request.FILES.get("file")
        since = _since(request.data.get("since"))
        manager_author = (request.data.get("manager_author") or "").strip()
        if upload is None or since is None or not manager_author:
            raise onboarding.StyleInputError("Faltan file, manager_author o since.")
        content = upload.read().decode("utf-8", errors="replace")
        supplier_id = request.data.get("supplier_id") or None
        onboarding.import_txt(
            content=content,
            manager_author=manager_author,
            since=since,
            supplier_id=int(supplier_id) if supplier_id else None,
            actor=request.user,
        )
        return self.state(status.HTTP_202_ACCEPTED)


class StyleTemplateView(StyleView):
    def post(self, request):
        onboarding.load_template_draft(actor=request.user)
        return self.state()


class StyleApproveView(StyleView):
    def post(self, request):
        approve_style(actor=request.user)
        return self.state()


class StyleVersionListView(StyleView):
    def get(self, request):
        owner = style_owner(request.user)
        versions = StyleVersion.objects.filter(user=owner)
        return Response(StyleVersionSerializer(versions, many=True).data)


class StyleVersionDetailView(StyleView):
    def get(self, request, pk):
        version = get_object_or_404(StyleVersion, pk=pk)
        return Response(StyleVersionDetailSerializer(version).data)


class StyleVersionRestoreView(StyleView):
    def post(self, request, pk):
        version = get_object_or_404(StyleVersion, pk=pk)
        restored = restore_style_version(version, actor=request.user)
        return Response(StyleVersionDetailSerializer(restored).data, status=status.HTTP_201_CREATED)


class StyleRefreshView(StyleView):
    def post(self, request):
        from .tasks_style import refresh_style

        refresh_style.delay()
        return Response({"detail": "Refresco encolado."}, status=status.HTTP_202_ACCEPTED)
