from django.urls import path

from . import views_onboarding

urlpatterns = [
    # Webhook, simulator, conversations and assistant endpoints arrive with B3 and B4 (backend).
    # WhatsApp onboarding (ADR 0011, B4.4): views owned by `orquestador` in views_onboarding.py.
    path(
        "onboarding/whatsapp/",
        views_onboarding.WhatsAppOnboardingView.as_view(),
        name="onboarding-whatsapp",
    ),
    path("onboarding/whatsapp/qr/", views_onboarding.WhatsAppQrView.as_view()),
    path("onboarding/whatsapp/webhook/", views_onboarding.WhatsAppWebhookView.as_view()),
]
