"""Django settings. Everything that differs per machine comes from the environment
(`.env` at the repo root, loaded by docker compose), see `.env.example`."""

from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, "dev-only-insecure-key-change-in-env"),
    DATABASE_URL=(str, "postgres://corpotex:corpotex@localhost:5432/corpotex"),
    REDIS_URL=(str, "redis://localhost:6379/0"),
    CLAUDE_CONFIG_DIR=(str, str(BASE_DIR / ".agent" / "config")),
    PUBLIC_BASE_URL=(str, "https://corpotex.oscargicast.com"),
    EVOLUTION_API_URL=(str, ""),
    EVOLUTION_INSTANCE=(str, "corpotex"),
    EVOLUTION_INSTANCE_TOKEN=(str, ""),
    EVOLUTION_WEBHOOK_SECRET=(str, ""),
    CF_ACCESS_CLIENT_ID=(str, ""),
    CF_ACCESS_CLIENT_SECRET=(str, ""),
    AGENT_MODEL=(str, "sonnet"),
    STYLE_ANALYSIS_MODEL=(str, "sonnet"),
    STYLE_BOSS_MODEL=(str, "opus"),
)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")

# The admin and the API are reached through the Next.js rewrite in development
# (host `web`) and through the Cloudflare tunnel in the demo (ADR 0023).
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "web", "host.docker.internal", "corpotex.oscargicast.com"]
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "https://corpotex.oscargicast.com",
]
CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3001"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "corsheaders",
    "core",
    "suppliers",
    "operations",
    "messaging",
    "manager",
    "agent",
    "seed",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "core.User"
AUTH_PASSWORD_VALIDATORS: list[dict] = []  # Demo accounts; the manager sets passwords in the admin.

LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["core.permissions.HasAnyRole"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": None,
    "PAGE_SIZE": None,
    "DATETIME_FORMAT": "iso-8601",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Corpotex API",
    "DESCRIPTION": "Supplier and workshop management with a WhatsApp agent.",
    "VERSION": "0.1.0",
    "COMPONENT_SPLIT_REQUEST": True,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
}

# Celery (ADR 0018): one worker on three queues, beat with a static schedule.
CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = None
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_DEFAULT_QUEUE = "turns"
CELERY_TASK_ROUTES = {
    "agent.tasks.run_turn": {"queue": "turns"},
    "manager.tasks.tick": {"queue": "periodic"},
    "core.tasks.run_style_extraction": {"queue": "style"},
    "core.tasks.refresh_style": {"queue": "style"},
}
CELERY_BEAT_SCHEDULE = {
    "tick": {"task": "manager.tasks.tick", "schedule": 10.0},
    "refresh_style": {"task": "core.tasks.refresh_style", "schedule": crontab(hour=3, minute=0)},
}
TURN_SOFT_TIME_LIMIT = 180

# Agent SDK (ADR 0010, 0013, 0022). The credential lives in CLAUDE_CONFIG_DIR,
# written by the dashboard (`/settings/claude`), never in the environment.
CLAUDE_CONFIG_DIR = env("CLAUDE_CONFIG_DIR")
AGENT_HOME = str(Path(CLAUDE_CONFIG_DIR).parent)
AGENT_MODEL = env("AGENT_MODEL")
STYLE_ANALYSIS_MODEL = env("STYLE_ANALYSIS_MODEL")
STYLE_BOSS_MODEL = env("STYLE_BOSS_MODEL")

# Evolution API (ADR 0001, 0006, 0010): instance token plus the Cloudflare Access service token.
EVOLUTION_API_URL = env("EVOLUTION_API_URL")
EVOLUTION_INSTANCE = env("EVOLUTION_INSTANCE")
EVOLUTION_INSTANCE_TOKEN = env("EVOLUTION_INSTANCE_TOKEN")
EVOLUTION_WEBHOOK_SECRET = env("EVOLUTION_WEBHOOK_SECRET")
CF_ACCESS_CLIENT_ID = env("CF_ACCESS_CLIENT_ID")
CF_ACCESS_CLIENT_SECRET = env("CF_ACCESS_CLIENT_SECRET")

PUBLIC_BASE_URL = env("PUBLIC_BASE_URL")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
