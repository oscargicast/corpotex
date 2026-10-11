from django.urls import path

from . import views, views_catalogue, views_claude, views_materials, views_style, views_follow_up

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("clock/", views.ClockView.as_view(), name="clock"),
    # Inventory (P0 of 10/10): manager and production.
    path("customers/", views_catalogue.CustomerListView.as_view(), name="customers"),
    path("products/", views_catalogue.ProductListView.as_view(), name="products"),
    path("materials/", views_materials.MaterialListView.as_view(), name="materials"),
    path("materials/<int:pk>/", views_materials.MaterialDetailView.as_view(), name="material-detail"),
    # Claude account (ADR 0022, B4.3): views owned by `orquestador` in core/views_claude.py.
    path("settings/follow-up/", views_follow_up.FollowUpSettingsView.as_view(), name="follow-up-settings"),
    path("settings/follow-up/preview/", views_follow_up.FollowUpPreviewView.as_view(), name="follow-up-preview"),
    path("settings/claude/", views_claude.ClaudeStatusView.as_view(), name="claude-status"),
    path("settings/claude/status/", views_claude.ClaudeStatusView.as_view()),
    path("settings/claude/start/", views_claude.ClaudeStartView.as_view()),
    path("settings/claude/exchange/", views_claude.ClaudeExchangeView.as_view()),
    path("settings/claude/set-key/", views_claude.ClaudeSetKeyView.as_view()),
    path("settings/claude/disconnect/", views_claude.ClaudeDisconnectView.as_view()),
    # Style onboarding and history: views owned by `personalidad` in core/views_style.py.
    path("onboarding/style/", views_style.OnboardingStyleView.as_view(), name="onboarding-style"),
    path("onboarding/style/extract/", views_style.StyleExtractView.as_view()),
    path("onboarding/style/import-txt/", views_style.StyleImportTxtView.as_view()),
    path("onboarding/style/template/", views_style.StyleTemplateView.as_view()),
    path("onboarding/style/approve/", views_style.StyleApproveView.as_view()),
    path("style/versions/", views_style.StyleVersionListView.as_view()),
    path("style/versions/<int:pk>/", views_style.StyleVersionDetailView.as_view()),
    path("style/versions/<int:pk>/restore/", views_style.StyleVersionRestoreView.as_view()),
    path("style/refresh/", views_style.StyleRefreshView.as_view()),
]
