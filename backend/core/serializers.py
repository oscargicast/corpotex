"""Shared serializer helpers and the role filter.

`serializer_for(model, role, detail=False)` returns the serializer class a role may use: the
manager sees everything; `sales` and `production` never get prices, payments, phone numbers nor
the free text where those leak (terms, rationale, candidates, decision summaries, supplier
notes). The dashboard views and the assistant's read tools go through the same classes
(ADR 0017)."""

from rest_framework import serializers

from .models import StyleVersion, User

# Fields only the manager may read, whatever the serializer.
MANAGER_ONLY_FIELDS = frozenset(
    {
        "unit_price",
        "total_amount",
        "terms",
        "rationale",
        "scores",
        "candidates",
        "payments",
        "conversation_id",
        "conversation",
        "last_message",
        "report_token",
        "report_url",
        "paid_amount",
        "pending_amount",
        "payments_summary",
        "payments_by_supplier",
        "numbers",
        "notes",
        "source_detail",
        "rates",
        "ratings",
        "rate_unit_price",
        "summary",
        "detail",
        "pending_decision",
    }
)


class RelativeFileField(serializers.FileField):
    """`/media/...` without host: the dashboard reaches Django through a rewrite or the tunnel."""

    def to_representation(self, value):
        return value.url if value else None


class DisplayMixin:
    """Adds `<field>_display` for every choice field listed in `Meta.display_fields` (declared
    as real fields so the OpenAPI schema carries them), and strips manager-only fields from
    every nested payload when the context role is not the manager (nested serializers do not
    go through `serializer_for`)."""

    def get_fields(self):
        fields = super().get_fields()
        for name in getattr(self.Meta, "display_fields", ()):
            if name in fields:
                fields[f"{name}_display"] = serializers.CharField(read_only=True, default="")
        return fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for name in getattr(self.Meta, "display_fields", ()):
            if name in data:
                getter = getattr(instance, f"get_{name}_display", None)
                data[f"{name}_display"] = getter() if getter else data[name]
        # Fail closed: only an explicit manager role keeps the manager-only keys.
        if self.context.get("role") != "manager":
            data = strip_manager_only(data)
        return data


def strip_manager_only(payload):
    """Recursively drops the manager-only keys. Role-aware top-level serializers already
    omit them; this covers nested lists such as items, rates or payments."""
    if isinstance(payload, dict):
        return {k: strip_manager_only(v) for k, v in payload.items() if k not in MANAGER_ONLY_FIELDS}
    if isinstance(payload, list):
        return [strip_manager_only(v) for v in payload]
    return payload


_ROLE_CACHE: dict[tuple, type] = {}
_REGISTRY: dict[tuple, type] = {}


def register(model, *, detail: bool = False):
    """Decorator: the serializer class for `model` (list or detail)."""

    def wrap(cls):
        _REGISTRY[(model, detail)] = cls
        return cls

    return wrap


def _load_registry() -> None:
    """Serializer modules register themselves on import; views only import this helper."""
    from django.utils.module_loading import autodiscover_modules

    autodiscover_modules("serializers")


def serializer_for(model, role: str | None, *, detail: bool = False):
    if (model, detail) not in _REGISTRY:
        _load_registry()
    base = _REGISTRY[(model, detail)]
    if role == "manager":
        return base
    key = (base, role)
    if key not in _ROLE_CACHE:
        allowed = [f for f in base.Meta.fields if f not in MANAGER_ONLY_FIELDS]
        meta = type("Meta", (base.Meta,), {"fields": allowed})
        _ROLE_CACHE[key] = type(f"{base.__name__}For{(role or 'anonymous').title()}", (base,), {"Meta": meta})
    return _ROLE_CACHE[key]


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "role", "is_staff"]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class LoginResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = UserSerializer()


class ClockSerializer(serializers.Serializer):
    now = serializers.DateTimeField(read_only=True)
    factor = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    paused = serializers.BooleanField(read_only=True)


class StyleVersionSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = StyleVersion
        fields = ["id", "source", "source_display", "changelog", "created_at"]


class StyleVersionDetailSerializer(StyleVersionSerializer):
    class Meta(StyleVersionSerializer.Meta):
        fields = StyleVersionSerializer.Meta.fields + ["style_md", "notes_snapshot"]
