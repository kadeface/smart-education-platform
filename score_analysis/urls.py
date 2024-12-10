from django.urls import path
from .views import (
    exam_list_view,
    exam_statistics_view,
    get_exam_statistics,
    export_statistics
)
app_name = 'score_analysis'
urlpatterns = [
    path('', exam_list_view, name='exam_list'),
    path('exam/<str:exam_id>/statistics/', exam_statistics_view, name='exam_statistics'),
    path('api/statistics/', get_exam_statistics, name='get_statistics'),
    path('export/', export_statistics, name='export_statistics'),
]

