from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_scores, name='home'),
    path('scores/', views.score_list, name='score_list'),
    path('upload/', views.upload_scores, name='upload_scores'),
    path('clean-data/', views.clean_data, name='clean_data'),
    path('start-mapping/', views.start_mapping, name='start_mapping'),
    path('process-scores/', views.process_scores, name='process_scores'),
    path('save-scores/', views.save_scores, name='save_scores'),
]