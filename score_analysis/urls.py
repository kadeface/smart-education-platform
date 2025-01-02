#score_analysis/urls.py
from django.urls import path
from .views import (
    exam_list_view,
    exam_statistics_view,
    get_exam_statistics,
    export_statistics
)
from .views.client import (client_exam_list,
                     client_exam_detail,
                      view_statistics_result
                    )
from score_analysis.views.indicators import basic_indicators
from score_analysis.views.tracking_view import TrackingAnalysisView
from .views.layer_view import LayerView
from .views.tracking_view import (ScoreRankingView,
                                  ScoreTrendView,
                                  StudentGroupView,
                                  WarningPredictionView)

app_name = 'score_analysis'
urlpatterns = [
    path('', exam_list_view, name='exam_list'),
    path('exam/<str:exam_id>/statistics/', exam_statistics_view, name='exam_statistics'),
    path('api/statistics/', get_exam_statistics, name='get_statistics'),
    path('export/', export_statistics, name='export_statistics'),
    #客户端页面的显示
    # 客户端 URLs
    path('client/', client_exam_list, name='client_exam_list'),  # 列表页
    path('client/<str:exam_id>/', client_exam_detail, name='client_exam_detail'),  # 详情页
    #path('client/statistics/', view_statistics_result, name='view_statistics_result'),  # 统计结果
    path('statistics-result/<str:exam_id>/', view_statistics_result, name='view_statistics_result'),

    #四个client基础模块的跳转定向
    path('region/layer/<str:module_type>/<str:exam_id>/',
         LayerView.as_view(),
         name='layer_view'), #区域分析模块

    path('indicators/basic/<str:module_type>/<str:exam_id>/',
         basic_indicators.view_basic_indicators,
         name='view_basic_indicators'), #质量监测模块

    path('tracking/analysis/<str:module_type>/<str:exam_id>/',
         TrackingAnalysisView.as_view(),
         name='view_development'),    #发展跟踪模块
    # 发展跟踪的子功能模块
    path('tracking/scores/<str:module_type>/<str:exam_id>/',
         ScoreRankingView.as_view(),
         name='score_ranking'),

    path('tracking/trends/<str:module_type>/<str:exam_id>/',
         ScoreTrendView.as_view(),
         name='score_trends'),

    path('tracking/groups/<str:module_type>/<str:exam_id>/',
         StudentGroupView.as_view(),
         name='student_groups'),

    path('tracking/warnings/<str:module_type>/<str:exam_id>/',
         WarningPredictionView.as_view(),
         name='warnings'),

 #   path('api/statistics/data/', StatisticsDataAPIView.as_view(), name='statistics-data'),
]

