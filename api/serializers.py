from .models import Curio, Clip, Tag
from rest_framework import serializers

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

class ClipListSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()
    curio_name = serializers.CharField(source="curio.name", read_only=True)
    percent_match = serializers.SerializerMethodField()

    class Meta:
        model = Clip
        fields = [
            "id", "platform_video_id", "url", "title", "summary", "transcript", "thumbnail_url", "platform",
            "created_at", "is_favorite", "curio", "curio_name", "description", "tags", "percent_match"
        ]

    def get_tags(self, obj):
        return list(obj.cliptag_set.values_list('tag__name', flat=True))
    
    def get_percent_match(self, obj):
        # Get from serializer context if available
        percent_map = self.context.get("percent_match_map", {})
        return percent_map.get(str(obj.id), None)