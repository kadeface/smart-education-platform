# score_analysis/models/indicators.py

from django.db import models

class BaseIndicatorModel(models.Model):
    """指标分析基础模型"""
    class Meta:
        abstract = True