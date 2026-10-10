"""Style onboarding and version history. Owned by the `personalidad` session (planning B4.6,
B4.7, B5.3); these stubs keep the URLs registered until the real views land."""

from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsManager


class NotImplementedView(APIView):
    permission_classes = [IsManager]

    def _todo(self, request, *args, **kwargs):
        return Response({"detail": "Pendiente: lo implementa personalidad (B4.6/B4.7)."}, status=501)

    get = post = put = _todo


class OnboardingStyleView(NotImplementedView):
    pass


class StyleExtractView(NotImplementedView):
    pass


class StyleImportTxtView(NotImplementedView):
    pass


class StyleTemplateView(NotImplementedView):
    pass


class StyleApproveView(NotImplementedView):
    pass


class StyleVersionListView(NotImplementedView):
    pass


class StyleVersionDetailView(NotImplementedView):
    pass


class StyleVersionRestoreView(NotImplementedView):
    pass


class StyleRefreshView(NotImplementedView):
    pass
