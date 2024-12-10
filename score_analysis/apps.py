# score_analysis/apps.py
from django.apps import AppConfig

class ScoreAnalysisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'score_analysis'
    verbose_name = '教学质量综合分析'
    def ready(self):
        """确保模板标签被正确加载"""
        import score_analysis.templatetags.score_analysis_tags