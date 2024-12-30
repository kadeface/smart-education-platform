# score_analysis/services/indicators.py

from django.contrib import admin
from score_analysis.admin import StatisticsExamIndicatorsAdmin
from score_analysis.models.statistics import StatisticsExamIndicators


class IndicatorService:
    """指标分析服务"""

    @staticmethod
    def get_admin_instance():
        """获取 StatisticsExamIndicatorsAdmin 实例"""
        return StatisticsExamIndicatorsAdmin(
            model=StatisticsExamIndicators,
            admin_site=admin.site
        )

    @classmethod
    def init_request(cls, request, module_type=None, grade=None):
        """初始化请求"""
        # 设置前台标记
        request.is_frontend = True

        # 存储额外信息到 session
        if module_type:
            request.session['current_module'] = module_type
        if grade:
            request.session['current_grade'] = grade

    @classmethod
    def get_statistics(cls, request, exam_id):
        """获取统计数据"""
        model_admin = cls.get_admin_instance()
        cls.init_request(request)
        return model_admin.view_statistics(request, exam_id)