from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Curio, Clip, ClipProcessingTask
from .serializers import CurioCreateSerializer, ClipCreateSerializer
from .tasks import process_clip_task 


class CurioCreateView(generics.CreateAPIView):
    serializer_class = CurioCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # Use your user_id from JWT or request
        serializer.save(user_id=self.request.user.id)


class ClipCreateView(generics.CreateAPIView):
    serializer_class = ClipCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # Only save url and (optional) curio
        clip = serializer.save(user_id=self.request.user.id)
        # Start async processing via Celery
        celery_task = process_clip_task.delay(clip.id)
        ClipProcessingTask.objects.create(
            clip=clip,
            celery_task_id=celery_task.id,
            status='pending'
        )

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        clip_id = response.data['id']
        task = ClipProcessingTask.objects.get(clip_id=clip_id)
        response.data['processing_status_url'] = f"/api/clip-status/{task.id}/"
        return response


class ClipProcessingStatusView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    queryset = ClipProcessingTask.objects.all()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        data = {
            'clip_id': instance.clip.id,
            'task_status': instance.status,
            'error': instance.error,
            'updated_at': instance.updated_at,
        }
        return Response(data)