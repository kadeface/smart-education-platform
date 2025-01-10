# score_analysis/services/indicators.py
from django.shortcuts import render
from score_analysis.views.generatestatsview import GenerateStatsView


class IndicatorService:
    """指标分析服务"""

    @classmethod
    def init_request(cls, request, module_type=None):
        """初始化请求"""
        # 存储额外信息到 session
        if module_type:
            request.session['current_module'] = module_type

    @classmethod
    def get_statistics(cls, request, exam_id):
        """获取统计数据"""
        try:
            # 使用 GenerateStatsView 处理请求
            view = GenerateStatsView.as_view()
            return view(request, exam_id=exam_id)

        except Exception as e:
            print(f"Error in get_statistics: {str(e)}")
            return render(request, 'score_analysis/client/error.html', {
                'error_message': f'获取统计数据时发生错误: {str(e)}'
            })