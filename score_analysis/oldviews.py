# score_analysis/templates/oldviews.py
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from score_analysis.services.t_score_calculator import TScoreCalculator
from score_analysis.services.ranking_calculator import RankingCalculator
from score_analysis.services.statistics_calculator import StatisticsCalculator
from score_analysis.models import SubjectTScore, ScoreRankings,BaseExamConfig
import logging

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
def calculate_t_scores(request):
    """触发T分计算"""
    try:
        exam_id = request.POST.get('exam_id')
        if not exam_id:
            return JsonResponse({'error': '考试ID不能为空'}, status=400)

        calculator = TScoreCalculator(exam_id=exam_id)
        calculator.calculate()

        return JsonResponse({'message': 'T分计算完成'})

    except Exception as e:
        logger.error(f"T分计算错误: {str(e)}")
        return JsonResponse({'error': f'T分计算失败: {str(e)}'}, status=500)


@require_http_methods(["GET"])
def get_t_scores(request):
    """查询T分结果"""
    try:
        exam_id = request.GET.get('exam_id')
        student_id = request.GET.get('student_id')
        subject_id = request.GET.get('subject_id')

        if not exam_id:
            return JsonResponse({'error': '考试ID不能为空'}, status=400)

        # 构建查询条件
        filters = {'exam_id': exam_id}
        if student_id:
            filters['unified_student_id'] = student_id
        if subject_id:
            filters['subject_id'] = subject_id

        # 查询T分
        scores = SubjectTScore.objects.filter(**filters).values(
            'exam_id',
            'unified_student_id',
            'subject_id',
            'stream_type',
            'level_type',
            'raw_score',
            't_score'
        )

        return JsonResponse({'data': list(scores)})

    except Exception as e:
        logger.error(f"查询T分错误: {str(e)}")
        return JsonResponse({'error': f'查询失败: {str(e)}'}, status=500)


@require_http_methods(["POST"])
def calculate_rankings(request):
    """计算排名"""
    try:
        exam_id = request.POST.get('exam_id')
        if not exam_id:
            return JsonResponse({'error': '考试ID不能为空'}, status=400)

        calculator = RankingCalculator(exam_id=exam_id)
        calculator.calculate()

        return JsonResponse({'message': '排名计算完成'})

    except Exception as e:
        logger.error(f"排名计算错误: {str(e)}")
        return JsonResponse({'error': f'排名计算失败: {str(e)}'}, status=500)


@require_http_methods(["GET"])
def get_rankings(request):
    """查询排名"""
    try:
        # 获取查询参数
        exam_id = request.GET.get('exam_id')
        subject_id = request.GET.get('subject_id')
        level_type = request.GET.get('level_type')
        stream_type = request.GET.get('stream_type')
        student_id = request.GET.get('student_id')

        if not exam_id:
            return JsonResponse({'error': '考试ID不能为空'}, status=400)

        # 构建查询条件
        filters = {'exam_id': exam_id}

        if subject_id:
            filters['subject_id'] = subject_id
        if level_type:
            filters['level_type'] = level_type
        if stream_type:
            filters['stream_type'] = stream_type
        if student_id:
            filters['unified_student_id'] = student_id

        # 查询排名
        rankings = ScoreRankings.objects.filter(**filters).values(
            'exam_id',
            'unified_student_id',
            'subject_id',
            'stream_type',
            'level_type',
            'raw_score',
            'raw_score_rank',
            'total_count',
            'percentile'
        ).order_by('subject_id', 'level_type', 'raw_score_rank')

        return JsonResponse({'data': list(rankings)})

    except Exception as e:
        logger.error(f"查询排名错误: {str(e)}")
        return JsonResponse({'error': f'查询失败: {str(e)}'}, status=500)


@require_http_methods(["GET"])
def get_total_rankings(request):
    """查询总分排名"""
    try:
        exam_id = request.GET.get('exam_id')
        level_type = request.GET.get('level_type')
        stream_type = request.GET.get('stream_type')
        student_id = request.GET.get('student_id')

        if not exam_id:
            return JsonResponse({'error': '考试ID不能为空'}, status=400)

        # 构建查询条件
        filters = {
            'exam_id': exam_id,
            'subject_id': 'total'  # 总分的subject_id为'total'
        }

        if level_type:
            filters['level_type'] = level_type
        if stream_type:
            filters['stream_type'] = stream_type
        if student_id:
            filters['unified_student_id'] = student_id

        # 查询总分排名
        rankings = ScoreRankings.objects.filter(**filters).values(
            'exam_id',
            'unified_student_id',
            'stream_type',
            'level_type',
            'raw_score',
            'raw_score_rank',
            'total_count',
            'percentile'
        ).order_by('level_type', 'raw_score_rank')

        return JsonResponse({'data': list(rankings)})

    except Exception as e:
        logger.error(f"查询总分排名错误: {str(e)}")
        return JsonResponse({'error': f'查询失败: {str(e)}'}, status=500)


@require_http_methods(["GET"])
def get_basic_statistics(request):
    """获取基础统计数据"""
    try:
        exam_id = request.GET.get('exam_id')
        if not exam_id:
            return JsonResponse({'error': '考试ID不能为空'}, status=400)

        calculator = StatisticsCalculator(exam_id=exam_id)
        stats = calculator.calculate_basic_statistics()

        return JsonResponse({
            'success': True,
            'data': stats
        })

    except Exception as e:
        logger.error(f"获取基础统计数据错误: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'获取基础统计数据失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def get_score_segments(request):
    """获取分数段统计数据"""
    try:
        exam_id = request.GET.get('exam_id')
        level_type = request.GET.get('level_type', 'city')  # 默认市级

        if not exam_id:
            return JsonResponse({'error': '考试ID不能为空'}, status=400)

        calculator = StatisticsCalculator(exam_id=exam_id)
        segments = calculator.calculate_score_segments()

        return JsonResponse({
            'success': True,
            'data': segments
        })

    except Exception as e:
        logger.error(f"获取分数段统计数据错误: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'获取分数段统计数据失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def get_district_statistics(request):
    """获取区域统计数据"""
    try:
        exam_id = request.GET.get('exam_id')
        district_name = request.GET.get('district_name')

        if not exam_id:
            return JsonResponse({'error': '考试ID不能为空'}, status=400)

        calculator = StatisticsCalculator(exam_id=exam_id)
        stats = calculator.calculate_basic_statistics()

        # 如果指定了区域，则只返回该区域的统计数据
        if district_name and 'district_statistics' in stats:
            district_stats = {
                district_name: stats['district_statistics'].get(district_name, {})
            }
            stats['district_statistics'] = district_stats

        return JsonResponse({
            'success': True,
            'data': stats
        })

    except Exception as e:
        logger.error(f"获取区域统计数据错误: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'获取区域统计数据失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def get_stream_distribution(request):
    """获取文理科分布数据"""
    try:
        exam_id = request.GET.get('exam_id')
        level_type = request.GET.get('level_type', 'city')  # 默认市级

        if not exam_id:
            return JsonResponse({'error': '考试ID不能为空'}, status=400)

        calculator = StatisticsCalculator(exam_id=exam_id)
        stats = calculator.calculate_basic_statistics()

        return JsonResponse({
            'success': True,
            'data': {
                'stream_distribution': stats.get('stream_distribution', {})
            }
        })

    except Exception as e:
        logger.error(f"获取文理科分布数据错误: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'获取文理科分布数据失败: {str(e)}'
        }, status=500)
# 添加新的模板视图函数
def index(request):
    """首页视图"""
    return render(request, 'index.html')

def rankings_list(request):
    """排名列表页面"""
    return render(request, 'rankingslist.html')

def statistics_basic(request):
    """基础统计页面"""
    return render(request, 'statistics_basic.html')


@require_http_methods(["GET"])
def get_exam_list(request):
    """获取考试列表"""
    try:
        logger.info("开始获取考试列表")
        exams = BaseExamConfig.objects.filter(
            status='active'  # 只获取激活状态的考试
        ).order_by(
            '-exam_date'  # 按日期降序排列
        ).values(
            'exam_id',
            'exam_name',
            'exam_date',
            'exam_type',
            'grade_level',
            'semester'
        )
        # 记录获取到的数据数量
        logger.info(f"获取到 {len(exams)} 条考试记录")
        return JsonResponse({'data': list(exams)})
    except Exception as e:
        logger.error(f"获取考试列表错误: {str(e)}")
        return JsonResponse({'error': f'获取考试列表失败: {str(e)}'}, status=500)


