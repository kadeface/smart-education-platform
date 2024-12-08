# score_analysis/models/base.py
#from django.db import models

from score_processor.models import (
    BaseExamConfig as BaseExamConfigModel,
    BaseSubjectConfig as BaseSubjectConfigModel,
    BaseSchoolInfo as BaseSchoolInfoModel
)

class BaseExamConfig(BaseExamConfigModel):
    """
    考试配置代理模型
    """
    class Meta:
        proxy = True

class BaseSubjectConfig(BaseSubjectConfigModel):
    """
    科目配置代理模型
    """
    class Meta:
        proxy = True

class BaseSchoolInfo(BaseSchoolInfoModel):
    """
    学校信息代理模型
    """
    class Meta:
        proxy = True

