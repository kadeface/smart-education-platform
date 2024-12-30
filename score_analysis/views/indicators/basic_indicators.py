# score_analysis/views/indicators/basic_indicators.py

from django.shortcuts import render
from score_analysis.services.indicators import IndicatorService


def view_basic_indicators(request, module_type, exam_id):
    """查看基础指标统计"""
    try:
        # 初始化请求
        IndicatorService.init_request(request, module_type)

        # 获取统计数据
        return IndicatorService.get_statistics(request, exam_id)

    except Exception as e:
        print(f"Error in view_basic_indicators: {str(e)}")
        return render(request, 'score_analysis/client/error.html', {
            'error_message': f'获取统计数据时发生错误: {str(e)}'
        })