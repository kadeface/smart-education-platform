# score_analysis/apps.py
from django.apps import AppConfig

class ScoreAnalysisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'score_analysis'
    verbose_name = '成绩分析'