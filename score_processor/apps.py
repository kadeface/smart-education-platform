from django.apps import AppConfig


class ScoreProcessorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'score_processor'
    verbose_name = '成绩处理'  # 在admin中显示的名称
