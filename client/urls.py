# client/urls.py
from django.urls import path
from . import views

app_name = 'client'

urlpatterns = [
    path('', views.client_home, name='client_home'),
    #path('grade-select/<str:module_type>/', views.grade_select, name='grade_select'),
    # 年级选择
    path('grade-select/<str:module_type>/', views.grade_select, name='grade_select'),

    # 考试选择
    path('exam-select/<str:module_type>/<str:grade>/', views.exam_select, name='exam_select'),

    # 分析页面
    path('analysis/<str:module_type>/<str:exam_id>/',
         views.analysis_view,
         name='analysis_view'),
]