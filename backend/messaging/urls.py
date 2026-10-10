from django.urls import path

from . import views, views_onboarding

urlpatterns = [
    # WhatsApp onboarding (ADR 0011, B4.4): views owned by `orquestador` in views_onboarding.py.
    path(
        "onboarding/whatsapp/",
        views_onboarding.WhatsAppOnboardingView.as_view(),
        name="onboarding-whatsapp",
    ),
    path("onboarding/whatsapp/qr/", views_onboarding.WhatsAppQrView.as_view()),
    path("onboarding/whatsapp/webhook/", views_onboarding.WhatsAppWebhookView.as_view()),
    # Simulator, conversations and the dashboard assistant (B3.8, B4.1).
    path("simulator/contacts/", views.SimulatorContactsView.as_view(), name="simulator-contacts"),
    path("simulator/messages/", views.SimulatorMessagesView.as_view(), name="simulator-messages"),
    path("conversations/<int:pk>/messages/", views.ConversationMessagesView.as_view(), name="conversation-messages"),
    path("assistant/messages/", views.AssistantMessagesView.as_view(), name="assistant-messages"),
    path("assistant/messages/read/", views.AssistantReadView.as_view(), name="assistant-read"),
    path("assistant/reset/", views.AssistantResetView.as_view(), name="assistant-reset"),
]
