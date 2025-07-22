from django.urls import path
from .views import (
    CurioCreateView, 
    ClipCreateView, 
    ClipProcessingStatusView,
    ClipSearchView,
    ProxyImageView,
    ClipDetailView,
    CurioListView,
    ClipFavoriteUpdateView,
    CurioFeedView,
    CurioPublicStatusUpdateView,
)


urlpatterns = [
    path('curios/', CurioCreateView.as_view(), name='curio-create'),
    path('curios/list/', CurioListView.as_view(), name='curio-list'),
    path('curios/feed/', CurioFeedView.as_view(), name='curio-feed'),
    path('curios/<uuid:id>/public/', CurioPublicStatusUpdateView.as_view(), name='curio-public-status-update'),
    path('clips/', ClipCreateView.as_view(), name='clip-create'),
    path('clip-status/<int:pk>/', ClipProcessingStatusView.as_view(), name='clip-status'),
    path('clips/search/', ClipSearchView.as_view(), name='clip-search'),
    path('clips/<uuid:id>/', ClipDetailView.as_view(), name='clip-detail'),
    path('proxy-image/', ProxyImageView.as_view(), name='proxy-image'),
    path('clips/<uuid:id>/favorite/', ClipFavoriteUpdateView.as_view(), name='clip-favorite-update'),
]