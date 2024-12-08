import os
from django.template.loader import get_template
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse, Http404
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from score_analysis.services.base_statistics import BaseStatisticsService  # 修改这里
from score_analysis.models import BaseExamConfig  # 修改这里
from score_analysis.services.exam_statistics import ExamStatisticsService
#from django.urls import reverse
# 定义考试类型选项
#url = reverse('score_analysis:exam_list')
@require_http_methods(["GET"])
def exam_list_view(request):
    """考试列表和统计数据主视图"""
    try:
        # 调试信息：打印模板相关的配置
        print("\n=== Template Configuration ===")
        print(f"BASE_DIR: {settings.BASE_DIR}")
        print(f"Template dirs: {settings.TEMPLATES[0]['DIRS']}")
        print(f"App dirs enabled: {settings.TEMPLATES[0]['APP_DIRS']}")
        print(f"Installed apps: {settings.INSTALLED_APPS}")

        # 检查模板文件是否存在
        template_path = os.path.join(settings.BASE_DIR, 'score_analysis', 'templates', 'score_analysis',
                                     'exam_overview.html')
        print(f"\n=== Template File Check ===")
        print(f"Looking for template at: {template_path}")
        print(f"Template exists: {os.path.exists(template_path)}")

        # 尝试加载模板
        print("\n=== Template Loading Test ===")
        try:
            template = get_template('score_analysis/exam_overview.html')
            print(f"Template found at: {template.origin.name}")
        except Exception as e:
            print(f"Template loading error: {str(e)}")

        # 获取筛选参数
        date_start = request.GET.get('date_start')
        date_end = request.GET.get('date_end')
        exam_type = request.GET.get('exam_type')
        quick_select = request.GET.get('quick_select')
        page = request.GET.get('page', 1)

        print("\n=== Request Parameters ===")
        print(f"date_start: {date_start}")
        print(f"date_end: {date_end}")
        print(f"exam_type: {exam_type}")
        print(f"quick_select: {quick_select}")
        print(f"page: {page}")

        # 构建查询条件
        exams_query = BaseExamConfig.objects.all().order_by('-exam_date')

        # 获取所有不同的考试类型
        exam_type_choices = BaseExamConfig.objects.values_list('exam_type', flat=True).distinct()
        print("\n=== Database Query ===")
        print(f"Total exams count: {exams_query.count()}")
        print(f"Available exam types: {list(exam_type_choices)}")

        # 应用筛选条件
        if date_start:
            exams_query = exams_query.filter(exam_date__gte=date_start)
        if date_end:
            exams_query = exams_query.filter(exam_date__lte=date_end)
        if exam_type:
            exams_query = exams_query.filter(exam_type=exam_type)

        print(f"Filtered exams count: {exams_query.count()}")

        # 分页处理
        paginator = Paginator(exams_query, 10)  # 每页10条
        current_page = paginator.get_page(page)

        context = {
            'exams': current_page,
            'exam_type_choices': [(t, t) for t in exam_type_choices if t],
            'filters': {
                'date_start': date_start,
                'date_end': date_end,
                'exam_type': exam_type,
                'quick_select': quick_select
            },
            'paginator': paginator,
            'current_page': current_page,
            'ranking_stats': {}  # 空的ranking_stats防止模板错误
        }

        print("\n=== Context Data ===")
        print(f"Context keys: {context.keys()}")
        print(f"Exam count in current page: {len(current_page)}")

        # 处理AJAX请求
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            print("\n=== AJAX Request ===")
            try:
                exams_html = render(request, 'score_analysis/partials/exam_list.html', context).content.decode('utf-8')
                print("Successfully rendered partial template")
                return JsonResponse({'success': True, 'exams_html': exams_html})
            except Exception as e:
                print(f"Error rendering partial template: {str(e)}")
                return JsonResponse({'success': False, 'message': str(e)})

        # 返回完整页面
        print("\n=== Rendering Full Page ===")
        return render(request, 'score_analysis/exam_list.html', context)

    except Exception as e:
        print(f"\n=== Error in exam_list_view ===")
        print(f"Error type: {type(e)}")
        print(f"Error message: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': str(e)})
        raise


@require_http_methods(["GET"])
def exam_statistics_view(request, exam_id):
    """考试统计分析页面"""
    try:
        # 获取考试信息
        exam = BaseExamConfig.objects.get(exam_id=exam_id)

        # 获取统计数据
        stats_service = ExamStatisticsService()
        statistics = stats_service.process_exam_statistics(exam_id)

        context = {
            'exam': exam,
            'statistics': statistics
        }

        return render(request, 'exam_statistics.html', context)

    except BaseExamConfig.DoesNotExist:
        context = {
            'error_message': f'未找到ID为 {exam_id} 的考试'
        }
        return render(request, 'error.html', context, status=404)

    except Exception as e:
        # 记录错误日志
        print(f"Error in exam_statistics_view: {str(e)}")
        context = {
            'error_message': '获取统计数据失败，请稍后重试'
        }
        return render(request, 'score_analysis/error.html', context, status=500)

@require_http_methods(["GET"])
def get_exam_statistics(request):
    """获取考试统计数据的API"""
    exam_id = request.GET.get('exam_id')
    if not exam_id:
        return JsonResponse({'success': False, 'message': '请选择考试'})

    try:
        stats_service = ExamStatisticsService()
        statistics = stats_service.process_exam_statistics(exam_id)

        context = {
            'exam_id': exam_id,
            'statistics': statistics
        }

        html_content = render(request,
                              'score_analysis/partials/stats_content.html',
                              context).content.decode('utf-8')

        return JsonResponse({
            'success': True,
            'html': html_content
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'获取统计数据失败：{str(e)}'
        })

@require_http_methods(["GET"])
def export_statistics(request):
    """导出统计数据"""
    exam_id = request.GET.get('exam_id')
    stream_type = request.GET.get('stream_type')
    
    if not exam_id:
        return JsonResponse({'success': False, 'message': '请选择考试'})
    
    try:
        # 导出逻辑待实现
        pass
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'导出失败: {str(e)}'
        })
    pass