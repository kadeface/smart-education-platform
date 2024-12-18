from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from ..models import BaseExamConfig
from ..services.exam_statistics import ExamStatisticsService
from ..admin import StatisticsExamIndicatorsAdmin
from django.contrib import admin
from ..models.statistics import (
    BaseExamConfig,
    StatisticsExamIndicators,  # 添加这个导入

)
from django.template.response import TemplateResponse  # 添加这行
@require_http_methods(["GET"])
def client_exam_list(request):
    """用户端考试列表视图"""
    exams = BaseExamConfig.objects.all().order_by('-exam_date')
    return render(request, 'score_analysis/client/exam_list.html', {
        'exams': exams
    })


@require_http_methods(["GET"])
def client_exam_detail(request, exam_id: str):  # 明确指定类型为str
    """用户端考试详情视图"""
    try:
        exam = BaseExamConfig.objects.get(exam_id=exam_id)
        stats_service = ExamStatisticsService()
        statistics = stats_service.process_exam_statistics(exam_id)

        return render(request, 'score_analysis/client/exam_detail.html', {
            'exam': exam,
            'statistics': statistics
        })
    except BaseExamConfig.DoesNotExist:
        return render(request, 'score_analysis/client/error.html', {
            'error_message': '未找到该考试'
        }, status=404)


@require_http_methods(["GET"])
def view_statistics_result(request, exam_id):
    """查看统计结果"""
    try:
        # 创建 StatisticsExamIndicatorsAdmin 实例
        model_admin = StatisticsExamIndicatorsAdmin(
            model=StatisticsExamIndicators,
            admin_site=admin.site
        )

        # 设置前台标记
        request.is_frontend = True

        # 直接使用后台的view_statistics方法
        return model_admin.view_statistics(request, exam_id)

    except Exception as e:
        return render(request, 'score_analysis/client/error.html', {
            'error_message': f'获取统计数据时发生错误: {str(e)}'
        })