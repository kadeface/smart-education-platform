# score_analysis/views/indicators/basic_indicators.py

from django.shortcuts import render

from score_analysis.views.exam_over_view import ExamOverviewView



def view_basic_indicators(request, module_type, exam_id):
    """查看基础指标统计"""
    try:
        # 创建 ExamOverviewView 实例
        view = ExamOverviewView()

        # 设置视图的必要属性
        view.request = request
        view.args = ()
        view.kwargs = {'exam_id': exam_id}

        # 获取上下文数据
        context = view.get_context_data(exam_id=exam_id)

        # 渲染模板
        return render(request, view.template_name, context)

    except Exception as e:
        print(f"Error in view_basic_indicators: {str(e)}")
        return render(request, 'score_analysis/client/error.html', {
            'error_message': f'获取统计数据时发生错误: {str(e)}'
        })