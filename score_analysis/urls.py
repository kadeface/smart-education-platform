#score_analysis/urls.py
from django.urls import path
from .views.frontend import frontend_exam_list, frontend_exam_detail,view_statistics_result  # 前台视图
from .views import (
    exam_list_view,
    exam_statistics_view,
    get_exam_statistics,
    export_statistics
)
from .views.api import StatisticsDataAPIView
app_name = 'score_analysis'
urlpatterns = [
    path('', exam_list_view, name='exam_list'),
    path('exam/<str:exam_id>/statistics/', exam_statistics_view, name='exam_statistics'),
    path('api/statistics/', get_exam_statistics, name='get_statistics'),
    path('export/', export_statistics, name='export_statistics'),
    path('exams/', frontend_exam_list, name='frontend_exam_list'),
    path('exam/<str:exam_id>/', frontend_exam_detail, name='frontend_exam_detail'),
    path('statistics-result/<str:exam_id>/', view_statistics_result, name='view_statistics_result'),
    #   path('api/statistics/data/', StatisticsDataAPIView.as_view(), name='statistics-data'),
]

