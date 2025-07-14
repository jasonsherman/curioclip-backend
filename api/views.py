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
from rest_framework.views import APIView
from django.http import StreamingHttpResponse, HttpResponseBadRequest, HttpResponse
import requests
from urllib.parse import urlparse
from random import sample

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
        response.data['processing_status_url'] = f"/clip-status/{task.id}/"
        response.data['task_id'] = task.id
        return response

class ClipSearchView(ListAPIView):
    serializer_class = ClipListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None 

    def get(self, request, *args, **kwargs):
        # Prepare base queryset (user's clips)
        queryset = Clip.objects.filter(user_id=request.user.id)
        clips = list(queryset)  # Always initialize clips

        # Semantic search if keyword query
        q = request.query_params.get('q')
        percent_by_clip = {}
        if q:
            query_embedding = embed_texts(q, OPENAI_API_KEY)[0]
            matches = vector_search_clip_ids_with_similarity(query_embedding, top_n=30, threshold=0.15)
            matched_clip_ids = [m["clip_id"] for m in matches]
            percent_by_clip = {str(m["clip_id"]): m["percent_match"] for m in matches}
            queryset = queryset.filter(id__in=matched_clip_ids)
            clips = list(queryset)  # Update clips if semantic search is used
        
        # Tag filter
        tags_param = request.query_params.get('tags')
        if tags_param:
            tags = [t.strip() for t in tags_param.split(",") if t.strip()]
            if tags:
                clips = [c for c in clips if set(tags).intersection(set([t for t in c.cliptag_set.values_list('tag__name', flat=True)]))]

        # Platform filter
        platform_param = request.query_params.get('platform')
        if platform_param:
            platforms = [p.strip() for p in platform_param.split(',') if p.strip()]
            if platforms:
                clips = [c for c in clips if c.platform in platforms]

        # Curio filter
        curio_id = request.query_params.get('curio')
        if curio_id:
            clips = [c for c in clips if str(c.curio_id) == curio_id]

        # Favourites filter
        is_favorite = request.query_params.get('is_favorite')
        if is_favorite is not None:
            val = is_favorite.lower() == "true"
            clips = [c for c in clips if c.is_favorite == val]

        # Sorting
        sort = request.query_params.get('sort', 'recent')
        if sort == "recent":
            clips.sort(key=lambda c: c.created_at, reverse=True)
        elif sort == "favorites":
            clips = [c for c in clips if c.is_favorite]
            clips.sort(key=lambda c: c.created_at, reverse=True)
        elif sort == "trending":
            # For demo, sort by #ratings (add to Clip model/annotate in production)
            clips.sort(key=lambda c: getattr(c, "num_ratings", 0), reverse=True)

        # Paginate if desired, or slice manually
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

class ProxyImageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        url = request.GET.get('url')

        if not url:
            return HttpResponseBadRequest("Missing image URL.")

        try:
            # Fetch the image from external source
            response = requests.get(url, stream=True)
            content_type = response.headers.get("Content-Type", "image/jpeg")

            return HttpResponse(response.content, content_type=content_type)
        except Exception as e:
            return HttpResponse(f"Failed to fetch image: {str(e)}", status=500)

class ClipDetailView(generics.RetrieveAPIView):
    serializer_class = ClipListSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    queryset = Clip.objects.all()

    def get_queryset(self):
        # Only allow access to the user's own clips
        return Clip.objects.filter(user_id=self.request.user.id)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        response['Cache-Control'] = 'public, max-age=120'   
        return response

class CurioListView(ListAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        curios = Curio.objects.filter(user_id=request.user.id)
        data = []
        for curio in curios:
            clips = list(Clip.objects.filter(curio=curio))
            thumbnails = [c.thumbnail_url for c in clips if c.thumbnail_url]
            # Pick up to 4 random thumbnails
            thumbnails = sample(thumbnails, min(4, len(thumbnails))) if thumbnails else []
            data.append({
                'id': str(curio.id),
                'name': curio.name,
                'clipCount': len(clips),
                'thumbnails': thumbnails,
                'created_at': curio.created_at.isoformat() if curio.created_at else None,
                'updated_at': curio.updated_at.isoformat() if curio.updated_at else None,
            })
        return Response(data)