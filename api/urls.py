from django.urls import path
from .views import (
    CurioCreateView, 
    ClipCreateView, 
    ClipProcessingStatusView,
    ClipSearchView,
    ProxyImageView,
    ClipDetailView,
    CurioListView
)


urlpatterns = [
    path('curios/', CurioCreateView.as_view(), name='curio-create'),
    path('curios/list/', CurioListView.as_view(), name='curio-list'),
    path('clips/', ClipCreateView.as_view(), name='clip-create'),
    path('clip-status/<int:pk>/', ClipProcessingStatusView.as_view(), name='clip-status'),
    path('clips/search/', ClipSearchView.as_view(), name='clip-search'),
    path('clips/<uuid:id>/', ClipDetailView.as_view(), name='clip-detail'),
    path('proxy-image/', ProxyImageView.as_view(), name='proxy-image'),
]