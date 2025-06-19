from django.urls import path
from .views import (
    CurioCreateView, 
    ClipCreateView, 
    ClipProcessingStatusView,
    ClipSearchView
)


urlpatterns = [
    path('curios/', CurioCreateView.as_view(), name='curio-create'),
    path('clips/', ClipCreateView.as_view(), name='clip-create'),
    path('clip-status/<int:pk>/', ClipProcessingStatusView.as_view(), name='clip-status'),
    path('clips/search/', ClipSearchView.as_view(), name='clip-search'),
]