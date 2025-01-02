# views/trackingview.py

from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from django.db.models import Avg, Count, Max, Min
from ..models.Tracking import TrackingRecord
from django.db.models import F
from django.core.paginator import Paginator
from ..models.source import ScoreStudentBasic

class TrackingAnalysisView(View):
    """发展跟踪分析主页面视图"""
    template_name = 'score_analysis/tracking/analysis_main.html'


    def get(self, request, module_type, exam_id):
        """显示发展跟踪分析主页面"""
        try:
            # 从考试ID中提取学段信息（例如：202411-DIST-H-2025 中的 H）
            school_level = exam_id.split('-')[2]  # 获取学段标识 (H/M/P)

            exam_info = self.get_exam_info(exam_id)
            overview_data = self.get_exam_overview(exam_id)

            context = {
                'module_type': module_type,
                'exam_id': exam_id,
                'school_level': school_level,  # 从考试ID中提取的学段信息
                'exam_info': exam_info,
                'overview': overview_data,
                'modules': self.get_module_list()
            }
            return render(request, self.template_name, context)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    def get_exam_info(self, exam_id):
        """获取考试基本信息"""
        exam = TrackingRecord.objects.filter(exam_id=exam_id).first()
        if not exam:
            raise Exception("考试信息不存在")

        student_count = TrackingRecord.objects.filter(exam_id=exam_id).count()
        return {
            'exam_id': exam_id,
            'student_count': student_count,
            'create_time': exam.create_time
        }

    def get_exam_overview(self, exam_id):
        """获取考试概览数据"""
        records = TrackingRecord.objects.filter(exam_id=exam_id)

        # 计算平均分
        avg_score = records.aggregate(Avg('total_score'))['total_score__avg']

        # 计算进步人数（improvement > 0）
        improved_count = records.filter(improvement__gt=0).count()

        # 计算尖子生人数（总分排名前10%）
        total_students = records.count()
        top_rank = total_students // 10  # 前10%的排名
        top_count = records.filter(city_rank__lte=top_rank).count()

        return {
            'avg_score': round(avg_score, 2) if avg_score else 0,
            'improved_count': improved_count,
            'top_count': top_count,
            'total_students': total_students
        }

    def get_module_list(self):
        """获取功能模块列表"""
        return [
            {
                'id': 'scores',
                'name': '成绩排名查询',
                'icon': 'fas fa-search',
                'url': 'score_analysis:score_ranking',
                'description': '查询学生成绩、排名和T分情况'
            },
            {
                'id': 'trends',
                'name': '成绩变化趋势',
                'icon': 'fas fa-chart-line',
                'url': 'score_analysis:score_trends',
                'description': '分析学生成绩和排名的历史变化趋势'
            },
            {
                'id': 'groups',
                'name': '学生群体分析',
                'icon': 'fas fa-users',
                'url': 'score_analysis:student_groups',
                'description': '分析不同层次学生群体的表现'
            },
            {
                'id': 'warnings',
                'name': '预警与预测',
                'icon': 'fas fa-exclamation-triangle',
                'url': 'score_analysis:warnings',
                'description': '识别成绩异常和预测发展趋势'
            }
        ]


class ExamOverviewAPI(View):
    """考试概览数据API"""

    def get(self, request):
        exam_id = request.GET.get('exam_id')
        if not exam_id:
            return JsonResponse({'error': '缺少考试ID'}, status=400)

        records = TrackingRecord.objects.filter(exam_id=exam_id)

        # 获取统计数据
        stats = records.aggregate(
            avg_score=Avg('total_score'),
            avg_t_score=Avg('total_t_score'),
            max_score=Max('total_score'),
            min_score=Min('total_score')
        )

        # 计算进步人数
        improved_count = records.filter(improvement__gt=0).count()

        # 计算需要预警的人数（可以根据具体规则调整）
        warning_count = records.filter(
            improvement__lt=0,  # 成绩下降
            percentile__lt=0.3  # 低于30%分位
        ).count()

        return JsonResponse({
            'stats': {
                'avg_score': round(stats['avg_score'], 2) if stats['avg_score'] else 0,
                'avg_t_score': round(stats['avg_t_score'], 2) if stats['avg_t_score'] else 0,
                'max_score': stats['max_score'],
                'min_score': stats['min_score'],
                'improved_count': improved_count,
                'warning_count': warning_count
            }
        })
class ScoreRankingView(View):
    """成绩排名查询视图"""
    template_name = 'score_analysis/tracking/score_ranking.html'
    def get_subjects_by_school_level(self, school_level):
        """根据学段返回科目列表"""
        subjects = {
            'P': [  # 小学
                {'field': 'chinese', 'name': '语文'},
                {'field': 'math', 'name': '数学'},
                {'field': 'english', 'name': '英语'},
                {'field': 'science', 'name': '科学'}
            ],
            'M': [  # 初中
                {'field': 'chinese', 'name': '语文'},
                {'field': 'math', 'name': '数学'},
                {'field': 'english', 'name': '英语'},
                {'field': 'physics', 'name': '物理'},
                {'field': 'chemistry', 'name': '化学'},
                {'field': 'biology', 'name': '生物'},
                {'field': 'history', 'name': '历史'},
                {'field': 'politics', 'name': '政治'},
                {'field': 'geography', 'name': '地理'}
            ],
            'H': [  # 高中
                {'field': 'chinese', 'name': '语文'},
                {'field': 'math', 'name': '数学'},
                {'field': 'english', 'name': '英语'},
                {'field': 'physics', 'name': '物理'},
                {'field': 'chemistry', 'name': '化学'},
                {'field': 'biology', 'name': '生物'},
                {'field': 'history', 'name': '历史'},
                {'field': 'politics', 'name': '政治'},
                {'field': 'geography', 'name': '地理'}  # 添加地理科目
            ]
        }
        return subjects.get(school_level, [])

    def get(self, request, module_type, exam_id):
        try:
            # 获取查询参数
            search_student_id = request.GET.get('student_id', '')
            search_student_name = request.GET.get('student_name', '')
            sort_by = request.GET.get('sort_by', 'total_score')
            order = request.GET.get('order', 'desc')
            page = request.GET.get('page', 1)
            per_page = request.GET.get('per_page', 20)

            # 从考试ID中提取学段信息
            school_level = exam_id.split('-')[2]
            subjects = self.get_subjects_by_school_level(school_level)

            # 基础查询 - 先获取跟踪记录
            records = TrackingRecord.objects.filter(exam_id=exam_id)
            # 计算总人数（在分页之前）
            total_students = records.count()
            # 获取对应的基础信息
            basic_records = {
                record.student_id: record
                for record in ScoreStudentBasic.objects.filter(
                    exam_id=exam_id
                )
            }

            # 搜索条件
            if search_student_id:
                records = records.filter(student_id__icontains=search_student_id)
            if search_student_name:
                student_ids = ScoreStudentBasic.objects.filter(
                    exam_id=exam_id,
                    student_name__icontains=search_student_name
                ).values_list('student_id', flat=True)
                records = records.filter(student_id__in=student_ids)

            # 排序处理
            order_field = '-' + sort_by if order == 'desc' else sort_by
            records = records.order_by(order_field)

            # 分页
            paginator = Paginator(records, per_page)
            current_page = paginator.get_page(page)
            # 计算统计数据
            stats = {
                'total_students': total_students,  # 使用之前计算的总人数
                'avg_score': records.aggregate(Avg('total_score'))['total_score__avg'] or 0,
                'avg_t_score': records.aggregate(Avg('total_t_score'))['total_t_score__avg'] or 0,
                'rank_changes': {
                    'improved': records.filter(improvement__gt=0).count(),
                    'unchanged': records.filter(improvement=0).count(),
                    'declined': records.filter(improvement__lt=0).count()
                }
            }
            # 为每条记录添加学生基本信息
            for record in current_page:
                basic_info = basic_records.get(record.student_id)
                if basic_info:
                    record.student_name = basic_info.student_name
                    record.district_name = basic_info.district_name
                    record.school_name = basic_info.school_name
                    record.select_type = basic_info.select_type
                    # 添加科目成绩
                    for subject in subjects:
                        setattr(record, subject['field'],
                                getattr(basic_info, subject['field'], None))

            context = {
                'module_type': module_type,
                'exam_id': exam_id,
                'school_level': school_level,
                'subjects': subjects,
                'total_count': total_students,
                'current_page': current_page,
                'search_student_id': search_student_id,
                'search_student_name': search_student_name,
                'sort_by': sort_by,
                'order': order,
                'stats': stats,
                'sort_options': self.get_sort_options(subjects)
            }
            return render(request, self.template_name, context)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    def get_sort_options(self, subjects):
        """动态生成排序选项"""
        # 基础排序选项
        options = [
            {'value': 'total_score', 'label': '总分'},
            {'value': 'total_t_score', 'label': '总T分'},
            {'value': 'city_rank', 'label': '市排名'},
            {'value': 'district_rank', 'label': '区排名'},
            {'value': 'school_rank', 'label': '校排名'},
            {'value': 'improvement', 'label': '进步分'},
            {'value': 't_improvement', 'label': 'T分进步'}
        ]

        # 添加科目排序选项
        for subject in subjects:
            options.append({
                'value': subject['field'],
                'label': subject['name']
            })

        return options

    def get_statistics(self, exam_id):
        """获取统计数据"""
        try:
            # 获取跟踪记录数据
            records = TrackingRecord.objects.filter(exam_id=exam_id)

            # 计算基础统计数据
            total_students = records.count()
            avg_score = records.aggregate(Avg('total_score'))['total_score__avg'] or 0
            avg_t_score = records.aggregate(Avg('total_t_score'))['total_t_score__avg'] or 0

            # 计算进步人数
            improved_count = records.filter(improvement__gt=0).count()
            unchanged_count = records.filter(improvement=0).count()
            declined_count = records.filter(improvement__lt=0).count()

            # 计算分数段分布
            score_ranges = [
                (0, 60), (60, 70), (70, 80),
                (80, 90), (90, 100), (100, float('inf'))
            ]
            score_distribution = []
            for start, end in score_ranges:
                count = records.filter(
                    total_score__gte=start,
                    total_score__lt=end
                ).count()
                score_distribution.append({
                    'range': f'{start}-{end}',
                    'count': count,
                    'percentage': round(count * 100 / total_students, 1) if total_students > 0 else 0
                })

            return {
                'total_students': total_students,
                'avg_score': round(avg_score, 1),
                'avg_t_score': round(avg_t_score, 1),
                'rank_changes': {
                    'improved': improved_count,
                    'unchanged': unchanged_count,
                    'declined': declined_count
                },
                'score_distribution': score_distribution,
                # 可以根据需要添加更多统计数据
                'percentiles': {
                    'top_10': records.filter(percentile__gte=90).count(),
                    'top_20': records.filter(percentile__gte=80).count(),
                    'top_50': records.filter(percentile__gte=50).count()
                }
            }

        except Exception as e:
            # 如果出现错误，返回空的统计数据
            return {
                'total_students': 0,
                'avg_score': 0,
                'avg_t_score': 0,
                'rank_changes': {
                    'improved': 0,
                    'unchanged': 0,
                    'declined': 0
                },
                'score_distribution': [],
                'percentiles': {
                    'top_10': 0,
                    'top_20': 0,
                    'top_50': 0
                }
            }
class ScoreTrendView(View):
    """成绩变化趋势视图"""
    template_name = 'score_analysis/tracking/score_trends.html'

    def get(self, request, module_type, exam_id):
        try:
            records = TrackingRecord.objects.filter(exam_id=exam_id)
            context = {
                'module_type': module_type,
                'exam_id': exam_id,
                'records': records,
            }
            return render(request, self.template_name, context)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

class StudentGroupView(View):
    """学生群体分析视图"""
    template_name = 'score_analysis/tracking/student_groups.html'

    def get(self, request, module_type, exam_id):
        try:
            records = TrackingRecord.objects.filter(exam_id=exam_id)
            context = {
                'module_type': module_type,
                'exam_id': exam_id,
                'records': records,
            }
            return render(request, self.template_name, context)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

class WarningPredictionView(View):
    """预警与预测视图"""
    template_name = 'score_analysis/tracking/warnings.html'

    def get(self, request, module_type, exam_id):
        try:
            records = TrackingRecord.objects.filter(exam_id=exam_id)
            context = {
                'module_type': module_type,
                'exam_id': exam_id,
                'records': records,
            }
            return render(request, self.template_name, context)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)