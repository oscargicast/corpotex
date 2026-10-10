from rest_framework import serializers

from .models import StyleVersion, User


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


class ClockPatchSerializer(serializers.Serializer):
    factor = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    paused = serializers.BooleanField(required=False)
    advance_hours = serializers.FloatField(required=False)


class StyleVersionSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = StyleVersion
        fields = ["id", "source", "source_display", "changelog", "created_at"]


class StyleVersionDetailSerializer(StyleVersionSerializer):
    class Meta(StyleVersionSerializer.Meta):
        fields = StyleVersionSerializer.Meta.fields + ["style_md", "notes_snapshot"]
