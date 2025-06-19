from rest_framework import generics, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q, Case, When, Value, FloatField
from .models import Curio, Clip, Tag, ClipProcessingTask
from .serializers import CurioCreateSerializer, ClipCreateSerializer, ClipListSerializer
from .utils import embed_texts, vector_search_clip_ids_with_scores
from .tasks import process_clip_task 
from .constants import OPENAI_API_KEY
import os

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

class ClipSearchView(ListAPIView):
    serializer_class = ClipListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None 

    def get_queryset(self):
        queryset = Clip.objects.filter(user_id=self.request.user.id)

        # --- Keyword semantic search ---
        q = self.request.query_params.get('q')
        if q:
            query_embedding = embed_texts([q], OPENAI_API_KEY)[0]
            results = vector_search_clip_ids_with_scores(query_embedding)
            # results: list of (clip_id, similarity)
            clip_id_to_similarity = {clip_id: similarity for clip_id, similarity in results}
            clip_ids = list(clip_id_to_similarity.keys())
            queryset = queryset.filter(id__in=clip_ids)
            cases_similarity = [
                When(id=clip_id, then=Value(similarity))
                for clip_id, similarity in clip_id_to_similarity.items()
            ]
            cases_percent = [
                When(id=clip_id, then=Value((1 - similarity) * 100 if similarity is not None else None))
                for clip_id, similarity in clip_id_to_similarity.items()
            ]
            queryset = queryset.annotate(
                similarity=Case(
                    *cases_similarity,
                    default=Value(None),
                    output_field=FloatField()
                ),
                percent_match=Case(
                    *cases_percent,
                    default=Value(None),
                    output_field=FloatField()
                )
            )
        
        # --- Filter: tags (comma-separated) ---
        tags_param = self.request.query_params.get('tags')
        if tags_param:
            tags = [t.strip() for t in tags_param.split(",") if t.strip()]
            if tags:
                queryset = queryset.filter(cliptag__tag__name__in=tags).distinct()
        
        # --- Filter: platform ---
        platform = self.request.query_params.get('platform')
        if platform:
            queryset = queryset.filter(platform=platform)

        # --- Filter: is_favorite ---
        is_favorite = self.request.query_params.get('is_favorite')
        if is_favorite is not None:
            queryset = queryset.filter(is_favorite=is_favorite.lower() == "true")
        
        # --- Sorting ---
        sort = self.request.query_params.get('sort', 'recent')
        if sort == "recent":
            queryset = queryset.order_by('-created_at')
        elif sort == "favourites":
            queryset = queryset.filter(is_favorite=True).order_by('-created_at')
        elif sort == "trending":
            queryset = queryset.annotate(num_ratings=Count('curiorating')).order_by('-num_ratings', '-created_at')

        return queryset

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