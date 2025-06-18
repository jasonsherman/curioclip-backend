from rest_framework import serializers
from .models import Curio, Clip

class CurioCreateSerializer(serializers.ModelSerializer):
    # user_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Curio
        fields = ['name', 'description', 'is_public']
        # read_only_fields = ['id']

class ClipCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Clip
        fields = ['id', 'url', 'curio']
        read_only_fields = ['id']
        extra_kwargs = {'curio': {'required': False, 'allow_null': True}}