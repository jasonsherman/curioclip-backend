from rest_framework import generics, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q, Case, When, Value, FloatField
from .models import Curio, Clip, Tag, ClipProcessingTask
from .serializers import CurioCreateSerializer, ClipCreateSerializer, ClipListSerializer
from .utils import embed_texts, vector_search_clip_ids_with_similarity
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

    def get(self, request, *args, **kwargs):
        # Prepare base queryset (user's clips)
        queryset = Clip.objects.filter(user_id=request.user.id)

        # Semantic search if keyword query
        q = request.query_params.get('q')
        percent_by_clip = {}
        if q:
            query_embedding = embed_texts(q, OPENAI_API_KEY)[0]
            matches = vector_search_clip_ids_with_similarity(query_embedding, top_n=30, threshold=0.15)
            matched_clip_ids = [m["clip_id"] for m in matches]
            percent_by_clip = {str(m["clip_id"]): m["percent_match"] for m in matches}
            queryset = queryset.filter(id__in=matched_clip_ids)
        
          

        # Tag filter
        tags_param = request.query_params.get('tags')
        if tags_param:
            tags = [t.strip() for t in tags_param.split(",") if t.strip()]
            if tags:
                clips = [c for c in clips if set(tags).intersection(set([t for t in c.cliptag_set.values_list('tag__name', flat=True)]))]

        # Platform filter
        platform = request.query_params.get('platform')
        if platform:
            clips = [c for c in clips if c.platform == platform]

        # Curio filter
        curio_id = request.query_params.get('curio')
        if curio_id:
            clips = [c for c in clips if str(c.curio_id) == curio_id]

        # Favourites filter
        is_favorite = request.query_params.get('is_favorite')
        if is_favorite is not None:
            val = is_favorite.lower() == "true"
            clips = [c for c in clips if c.is_favorite == val]

        clips = list(queryset)

        # Sorting
        sort = request.query_params.get('sort', 'recent')
        if sort == "recent":
            clips.sort(key=lambda c: c.created_at, reverse=True)
        elif sort == "favourites":
            clips = [c for c in clips if c.is_favorite]
            clips.sort(key=lambda c: c.created_at, reverse=True)
        elif sort == "trending":
            # For demo, sort by #ratings (add to Clip model/annotate in production)
            clips.sort(key=lambda c: getattr(c, "num_ratings", 0), reverse=True)

        # Paginate if desired, or slice manually
        # (DRF pagination requires queryset; for semantic, you'd want to paginate after filtering)
        page = self.paginate_queryset(clips)
        serializer = self.get_serializer(page if page is not None else clips, many=True, context={"percent_match_map": percent_by_clip})
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
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