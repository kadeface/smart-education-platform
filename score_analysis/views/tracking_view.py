# views/trackingview.py
import numpy as np
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.db.models import (
    Count, F, Q, Case, When, Value, CharField,
    Avg, StdDev, FloatField,Max, Min,ExpressionWrapper
)
from django.db.models.functions import JSONObject, Cast
from score_processor.models import StudentMapping, BaseExamConfig
from ..models.Tracking import TrackingRecord
from django.db.models import F
from django.core.paginator import Paginator
from ..models.source import ScoreStudentBasic
from ..models.statistics import ExamLevelAnalysisConfig


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
    """成绩变化趋势视图。

    提供基于学生姓名查询的成绩发展趋势分析功能，包括整体趋势、学科贡献和分位跃迁分析。
    通过student_mapping表进行学生信息查询，使用unified_id关联tracking_record表获取成绩数据。

    Attributes:
        template_name (str): 模板文件路径
    """
    template_name = 'score_analysis/tracking/score_trends.html'

    def get(self, request, module_type: str, exam_id: str) -> HttpResponse:
        """处理学生成绩查询的GET请求。"""
        try:
            student_name = request.GET.get('student_name', '').strip()
            context = {
                'module_type': module_type,
                'exam_id': exam_id,
            }

            if student_name:
                print("\n=== 成绩查询 ===")
                print(f"查询参数: 学生姓名={student_name}, 考试ID={exam_id}")

                # 1. 在当前考试中查找该学生
                student = ScoreStudentBasic.objects.filter(
                    student_name__icontains=student_name,
                    exam_id=exam_id
                ).values(
                    'student_id',
                    'student_name',
                    'school_name',
                    'class_field',
                    'select_type'
                ).first()

                if student:
                    print(f"找到学生: {student['student_name']}, ID: {student['student_id']}")

                    # 2. 获取比较考试记录
                    exam_level = exam_id.split('-')[1]  # 获取考试级别 (CITY/DIST)

                    # 构建查询条件
                    exam_filter = {
                        'student_id': student['student_id'],
                    }

                    # 如果是市级考试，只比较市级考试
                    if exam_level == 'CITY':
                        exam_filter['exam_id__contains'] = '-CITY-'
                        print("当前是市级考试，只比较市级考试")
                    else:
                        print("当前是区级考试，比较所有考试")

                    # 获取所有符合条件的考试记录
                    all_exams = TrackingRecord.objects.filter(
                        **exam_filter
                    ).order_by('-exam_id')  # 按考试ID降序排序

                    # 打印所有找到的考试记录
                    print("\n找到的所有考试记录:")
                    for exam in all_exams:
                        print(f"考试ID: {exam.exam_id}, 时间: {exam.create_time}")

                    # 获取最近3次考试记录（不包括当前考试）
                    previous_exams = all_exams.exclude(
                        exam_id=exam_id
                    )[:3]

                    compare_exam_ids = list(previous_exams.values_list('exam_id', flat=True))

                    if compare_exam_ids:
                        print(f"\n选择的比较考试记录: {compare_exam_ids}")
                        # 将当前考试添加到比较列表
                        compare_exam_ids.insert(0, exam_id)
                        print(f"最终比较考试列表: {compare_exam_ids}")

                        context.update({
                            'selected_student': {
                                'id': student['student_id'],
                                'name': student['student_name'],
                                'school_name': student['school_name'],
                                'class_name': student['class_field'],
                                'student_number': student['student_id'],
                                'select_type': student['select_type']
                            },
                            'trend_data': self._get_trend_data(
                                student['student_id'],
                                exam_id,
                                compare_exam_ids
                            ),
                            'subject_analysis': self._get_subject_analysis(
                                student['student_id'],
                                exam_id,
                                exam_id.split('-')[2],
                                compare_exam_ids
                            ),
                            'percentile_data': self._get_percentile_data(
                                student['student_id'],
                                exam_id,
                                compare_exam_ids
                            )
                        })
                    else:
                        print("未找到之前的考试记录")
                        context.update({
                            'error_message': '未找到该学生之前的考试记录'
                        })

            return render(request, self.template_name, context)

        except Exception as e:
            error_msg = f"查询出错：{str(e)}"
            print(error_msg)
            import traceback
            print(traceback.format_exc())
            return JsonResponse({
                'error': error_msg,
                'debug_info': {
                    'student_name': student_name if 'student_name' in locals() else None,
                    'exam_id': exam_id,
                    'exception_type': type(e).__name__,
                    'traceback': traceback.format_exc()
                }
            }, status=500)
    def _get_available_exams(self, student_id: str, current_exam_id: str) -> list:
        """获取学生可比较的考试列表。

        Args:
            student_id: 学生ID
            current_exam_id: 当前考试ID

        Returns:
            list: 可比较的考试信息列表，按时间倒序排列
        """
        school_level = current_exam_id.split('-')[2]
        return TrackingRecord.objects.filter(
            student_id=student_id,
            exam_id__contains=f"-{school_level}-"  # 确保是同一学段
        ).order_by('-create_time').values(
            'exam_id',
            'create_time'
        ).distinct()

    def _format_exam_name(self, exam_id: str, create_time) -> str:
        """格式化考试名称。

        Args:
            exam_id: 考试ID
            create_time: 考试时间

        Returns:
            str: 格式化后的考试名称，格式：YYYY年QN 考试类型
        """
        quarter = (create_time.month - 1) // 3 + 1
        return f"{create_time.year}年Q{quarter} {exam_id.split('-')[1]}"

    def _get_trend_data(self, student_id: str, exam_id: str, compare_exam_ids: list) -> list:
        """获取整体趋势数据。"""
        from django.db.models import OuterRef, Subquery

        # 获取考试记录并关联考试名称
        records = TrackingRecord.objects.filter(
            student_id=student_id,
            exam_id__in=compare_exam_ids
        ).annotate(
            exam_name=Subquery(
                BaseExamConfig.objects.filter(
                    exam_id=OuterRef('exam_id')
                ).values('exam_name')[:1]
            )
        ).order_by('exam_id')  # 先按exam_id排序，后面会重新排序

        print("\n=== 趋势数据查询 ===")
        print(f"学生ID: {student_id}")
        print(f"比较考试: {compare_exam_ids}")

        # 将记录转换为列表并按考试ID的年月部分排序
        records_list = list(records)
        records_list.sort(key=lambda x: x.exam_id[:6], reverse=True)  # 按年月降序排序

        trend_data = []
        for i, record in enumerate(records_list):
            # 计算滚动均值（使用总分）
            if i == len(records_list) - 1:  # 最早的考试
                rolling_avg = None
            else:
                # 获取最近三次考试的记录（包括当前考试）
                recent_records = records_list[i:min(i + 3, len(records_list))]
                rolling_avg = round(sum(r.total_score for r in recent_records) / len(recent_records), 1)

            # 计算排名变化
            if i == len(records_list) - 1:  # 最早的考试
                rank_change = '-'
            else:
                next_rank = records_list[i + 1].city_rank  # 上一次考试的排名
                curr_rank = record.city_rank
                rank_diff = next_rank - curr_rank
                rank_change = f"↑{rank_diff}" if rank_diff > 0 else f"↓{abs(rank_diff)}"

            exam_name = record.exam_name or f"未知考试({record.exam_id})"
            print(f"考试: {exam_name}, ID: {record.exam_id}, 总分: {record.total_score}, 排名: {record.city_rank}")

            trend_data.append({
                'exam_period': exam_name,
                't_score': round(record.total_score, 1),
                'rolling_avg': rolling_avg,
                'city_rank': record.city_rank,
                'rank_change': rank_change
            })

        return trend_data

    def _get_subject_analysis(self, student_id: str, exam_id: str, school_level: str, compare_exam_ids: list) -> list:
        """获取学科贡献分析数据。"""
        print("\n=== 学科贡献分析 ===")
        print(f"学生ID: {student_id}")
        print(f"比较考试列表: {compare_exam_ids}")

        if len(compare_exam_ids) < 2:
            return []

        # 获取最新和最早的记录
        latest_record = TrackingRecord.objects.filter(
            student_id=student_id,
            exam_id=compare_exam_ids[0]
        ).first()

        earliest_record = TrackingRecord.objects.filter(
            student_id=student_id,
            exam_id=compare_exam_ids[-1]
        ).first()

        if not (latest_record and earliest_record):
            print("未找到完整的考试记录")
            return []

        subject_changes = []
        latest_scores = latest_record.subject_t_scores or {}
        earliest_scores = earliest_record.subject_t_scores or {}

        # 科目配置
        subject_config = {
            'math': {'name': '数学', 'max_score': 150},
            'chinese': {'name': '语文', 'max_score': 150},
            'english': {'name': '英语', 'max_score': 150},
            'physics': {'name': '物理', 'max_score': 100},
            'chemistry': {'name': '化学', 'max_score': 100},
            'biology': {'name': '生物', 'max_score': 100},
            'history': {'name': '历史', 'max_score': 100},
            'geography': {'name': '地理', 'max_score': 100},
            'politics': {'name': '政治', 'max_score': 100}
        }

        print("\n科目T分对比:")
        for field, config in subject_config.items():
            subject_name = config['name']
            max_score = config['max_score']
            latest_score = latest_scores.get(field)
            earliest_score = earliest_scores.get(field)

            print(f"\n{subject_name}:")
            print(f"  最新T分: {latest_score}")
            print(f"  最早T分: {earliest_score}")
            print(f"  满分值: {max_score}")

            # 初始化状态
            status = None
            change = 0
            weighted_change = 0

            if latest_score is not None and earliest_score is not None:
                try:
                    # 处理不同情况
                    if latest_score == -3 or earliest_score == -3:
                        status = "未参加"
                    elif latest_score == max_score and earliest_score == max_score:
                        status = "保持满分"
                        change = 0
                        weighted_change = 0
                    elif latest_score == 0 and earliest_score == 0:
                        status = "未参加"
                    else:
                        change = round(float(latest_score) - float(earliest_score), 1)
                        weighted_change = round(change * 0.3, 2)
                        status = "正常"

                    print(f"  状态: {status}")
                    print(f"  T分变化: {change}")
                    print(f"  权重贡献: {weighted_change}")
                except (ValueError, TypeError) as e:
                    print(f"  计算错误: {e}")
                    status = "数据错误"
            else:
                status = "缺少数据"
                print("  缺少T分数据")

            subject_changes.append({
                'subject': subject_name,
                't_score_change': "满分" if status == "保持满分" else
                "未参加" if status == "未参加" else
                f"+{change}" if change > 0 else f"{change}",
                'weighted_contribution': weighted_change,
                'status': status
            })

        # 排序规则：
        # 1. 有变化的科目（按贡献度绝对值降序）
        # 2. 保持满分的科目
        # 3. 未参加的科目
        def sort_key(x):
            if x['status'] == "正常":
                # 有变化的科目排在最前面，按贡献度绝对值排序
                return (0, abs(x['weighted_contribution']), x['subject'])
            elif x['status'] == "保持满分":
                # 保持满分的科目排在中间
                return (1, 0, x['subject'])
            else:  # 未参加或其他情况
                # 未参加的科目排在最后
                return (2, 0, x['subject'])

        sorted_changes = sorted(
            subject_changes,
            key=sort_key
        )

        # 调试输出排序结果
        print("\n排序后的科目列表:")
        for change in sorted_changes:
            print(
                f"{change['subject']}: {change['status']} - {change['t_score_change']} ({change['weighted_contribution']})")

        return sorted_changes

    def _get_percentile_data(self, student_id: str, exam_id: str, compare_exam_ids: list) -> dict:
        """获取分位跃迁分析数据。"""
        print(f"\n=== 分位跃迁分析 ===")
        print(f"学生ID: {student_id}")
        print(f"原始考试列表: {compare_exam_ids}")

        if len(compare_exam_ids) < 2:
            return {}

        # 按考试级别分组
        city_exams = [exam_id for exam_id in compare_exam_ids if 'CITY' in exam_id]
        dist_exams = [exam_id for exam_id in compare_exam_ids if 'DIST' in exam_id]

        print(f"市级考试: {city_exams}")
        print(f"区级考试: {dist_exams}")

        # 优先使用市级考试进行比较
        if len(city_exams) >= 2:
            compare_exams = city_exams
            exam_level = "市级"
        elif len(dist_exams) >= 2:
            compare_exams = dist_exams
            exam_level = "区级"
        else:
            print("没有足够的同级别考试进行比较")
            return {}

        # 按时间排序获取记录
        records = TrackingRecord.objects.filter(
            student_id=student_id,
            exam_id__in=compare_exams
        ).order_by('create_time')

        # 获取最早和最新的记录
        earliest_record = records.first()
        latest_record = records.last()

        if not (earliest_record and latest_record):
            print("未找到完整的考试记录")
            return {}

        print(f"比较{exam_level}考试:")
        print(f"最早考试: {earliest_record.exam_id}, 时间: {earliest_record.create_time}")
        print(f"最新考试: {latest_record.exam_id}, 时间: {latest_record.create_time}")

        # 获取同考试的所有记录
        same_exam_records = TrackingRecord.objects.filter(
            exam_id=latest_record.exam_id
        )
        total_count = same_exam_records.count()

        if total_count == 0:
            return {}

        # 计算超越人数（T分排名）
        surpass_count = same_exam_records.filter(
            total_t_score__lt=latest_record.total_t_score
        ).count()
        surpass_rate = round((surpass_count / total_count) * 100) if total_count > 0 else 0

        # 计算百分位
        if earliest_record.percentile is not None:
            earliest_percentile = round(earliest_record.percentile * 100)
        else:
            earliest_percentile = round(
                (1 - earliest_record.city_rank / total_count) * 100) if earliest_record.city_rank else 0

        if latest_record.percentile is not None:
            latest_percentile = round(latest_record.percentile * 100)
        else:
            latest_percentile = round(
                (1 - latest_record.city_rank / total_count) * 100) if latest_record.city_rank else 0

        print(f"{exam_level}百分位变化: {earliest_percentile}% -> {latest_percentile}%")
        print(f"{exam_level}超越率: {surpass_rate}%")

        return {
            'percentile_change': f"从{exam_level}前{earliest_percentile}% → 前{latest_percentile}%",
            'surpass_info': f"超越同分位组{surpass_rate}%的学生"
        }
    def _get_subjects_by_school_level(self, school_level: str) -> list:
        """根据学段返回科目列表。

        Args:
            school_level: 学段标识(H/M/P)

        Returns:
            list: 包含科目信息的字典列表
        """
        subjects = {
            'P': [
                {'field': 'chinese', 'name': '语文'},
                {'field': 'math', 'name': '数学'},
                {'field': 'english', 'name': '英语'},
                {'field': 'science', 'name': '科学'}
            ],
            'M': [
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
            'H': [
                {'field': 'chinese', 'name': '语文'},
                {'field': 'math', 'name': '数学'},
                {'field': 'english', 'name': '英语'},
                {'field': 'physics', 'name': '物理'},
                {'field': 'chemistry', 'name': '化学'},
                {'field': 'biology', 'name': '生物'},
                {'field': 'history', 'name': '历史'},
                {'field': 'politics', 'name': '政治'},
                {'field': 'geography', 'name': '地理'}
            ]
        }
        return subjects.get(school_level, [])


from django.views import View
from django.shortcuts import render
from django.http import JsonResponse
from django.db import connection
from decimal import Decimal
import json


class StudentGroupView(View):
    """学生群体分析视图类。

    该视图类处理学生群体分析相关的请求，包括群体统计、学校分布、
    学科分析和预警信息等功能。

    Attributes:
        template_name: 模板文件路径
    """

    template_name = 'score_analysis/tracking/student_groups.html'

    def get_thresholds(self, exam_id, select_type='理科'):
        """获取分数线阈值。

        从考试分层分析配置表获取特控群和本科群的分数线。

        Args:
            exam_id (str): 考试ID
            select_type (str): 分科类型，默认为'理科'

        Returns:
            dict: 包含特控和本科分数线的字典
                {
                    'special_score': float,  # 特控分数线
                    'regular_score': float   # 本科分数线
                }

        Raises:
            Exception: 当配置不存在时抛出异常
        """
        config = ExamLevelAnalysisConfig.objects.filter(
            exam_id=exam_id,
            select_type=select_type,
            is_active=True
        ).values('score_lines').first()

        if not config:
            raise Exception(f"未找到考试{exam_id}的{select_type}分数线配置")

        score_lines = config['score_lines']
        return {
            'special_score': float(score_lines.get('特控', 0)),
            'regular_score': float(score_lines.get('本科', 0))
        }

    def get_group_statistics(self, exam_id, select_type='理科', district_name='开平市', compare_exam_id=None):
        """获取群体统计数据。

        群体划分标准：
        - 特控群：分数 >= 特控线
        - 特控临界群：特控线 > 分数 >= 特控线-10
        - 本科群：分数 >= 本科线
        - 本科临界群：本科线 > 分数 >= 本科线-10
        """
        try:
            thresholds = self.get_thresholds(exam_id, select_type)

            # 定义群体顺序和名称
            group_order = ['special', 'special_margin', 'regular', 'regular_margin']
            group_names = {
                'special': '特控群',
                'special_margin': '特控临界群',
                'regular': '本科群',
                'regular_margin': '本科临界群'
            }

            # 获取当前考试的群体分布
            current_stats = ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                select_type=select_type,
                district_name=district_name
            ).aggregate(
                special=Count(
                    'id',
                    filter=Q(total_score__gte=thresholds['special_score'])
                ),
                special_margin=Count(
                    'id',
                    filter=Q(
                        total_score__lt=thresholds['special_score'],
                        total_score__gte=thresholds['special_score'] - 10
                    )
                ),
                regular=Count(
                    'id',
                    filter=Q(total_score__gte=thresholds['regular_score'])
                ),
                regular_margin=Count(
                    'id',
                    filter=Q(
                        total_score__lt=thresholds['regular_score'],
                        total_score__gte=thresholds['regular_score'] - 10
                    )
                )
            )

            # 如果没有指定比较考试，获取上一次考试ID
            if not compare_exam_id:
                previous_exam = ScoreStudentBasic.objects.filter(
                    exam_id__lt=exam_id,
                    select_type=select_type,
                    district_name=district_name
                ).values('exam_id').distinct().order_by('-exam_id').first()

                if previous_exam:
                    compare_exam_id = previous_exam['exam_id']

            print(f"当前考试: {exam_id}")
            print(f"比较考试: {compare_exam_id} ({'用户选择' if compare_exam_id else '默认上一次'})")
            print(f"查询条件: select_type={select_type}, district_name={district_name}")

            # 获取比较考试的群体分布
            previous_stats = {}
            if compare_exam_id:
                prev_thresholds = self.get_thresholds(compare_exam_id, select_type)
                previous_stats = ScoreStudentBasic.objects.filter(
                    exam_id=compare_exam_id,
                    select_type=select_type,
                    district_name=district_name
                ).aggregate(
                    special=Count(
                        'id',
                        filter=Q(total_score__gte=prev_thresholds['special_score'])
                    ),
                    special_margin=Count(
                        'id',
                        filter=Q(
                            total_score__lt=prev_thresholds['special_score'],
                            total_score__gte=prev_thresholds['special_score'] - 10
                        )
                    ),
                    regular=Count(
                        'id',
                        filter=Q(total_score__gte=prev_thresholds['regular_score'])
                    ),
                    regular_margin=Count(
                        'id',
                        filter=Q(
                            total_score__lt=prev_thresholds['regular_score'],
                            total_score__gte=prev_thresholds['regular_score'] - 10
                        )
                    )
                )

            # 按指定顺序整理返回数据
            from collections import OrderedDict
            group_stats = OrderedDict()

            for group_type in group_order:
                current_count = current_stats.get(group_type, 0)
                previous_count = previous_stats.get(group_type, 0)

                group_stats[group_type] = {
                    'name': group_names[group_type],
                    'current_count': current_count,
                    'change': current_count - previous_count,
                    'compare_exam_id': compare_exam_id  # 添加比较考试ID到返回数据
                }

            return group_stats

        except Exception as e:
            raise Exception(f"统计数据获取失败: {str(e)}")

    def get_school_distribution(self, exam_id, select_type='理科', district_name='开平市', compare_exam_id=None):
        """获取学校分布数据。"""
        try:
            thresholds = self.get_thresholds(exam_id, select_type)

            # 获取当前考试的学校分布，按本科人数降序排序
            current_distribution = ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                district_name=district_name,
                select_type=select_type
            ).values('school_name').annotate(
                student_count=Count('id'),
                regular_count=Count(  # 添加本科人数统计
                    'id',
                    filter=Q(total_score__gte=thresholds['regular_score'])
                ),
                group_distribution=JSONObject(
                    special=Count(
                        'id',
                        filter=Q(total_score__gte=thresholds['special_score'])
                    ),
                    special_margin=Count(
                        'id',
                        filter=Q(
                            total_score__lt=thresholds['special_score'],
                            total_score__gte=thresholds['special_score'] - 10
                        )
                    ),
                    regular=Count(
                        'id',
                        filter=Q(total_score__gte=thresholds['regular_score'])
                    ),
                    regular_margin=Count(
                        'id',
                        filter=Q(
                            total_score__lt=thresholds['regular_score'],
                            total_score__gte=thresholds['regular_score'] - 10
                        )
                    )
                )
            ).order_by('-regular_count', '-student_count')  # 首先按本科人数降序，其次按总人数降序

            # 如果没有指定比较考试，获取上一次考试ID
            if not compare_exam_id:
                previous_exam = ScoreStudentBasic.objects.filter(
                    exam_id__lt=exam_id,
                    select_type=select_type,
                    district_name=district_name
                ).values('exam_id').distinct().order_by('-exam_id').first()

                if previous_exam:
                    compare_exam_id = previous_exam['exam_id']

            print(f"当前考试: {exam_id}")
            print(f"比较考试: {compare_exam_id} ({'用户选择' if compare_exam_id else '默认上一次'})")

            # 如果有比较考试（用户选择或默认上一次），获取其分布数据
            if compare_exam_id:
                prev_thresholds = self.get_thresholds(compare_exam_id, select_type)

                previous_distribution = ScoreStudentBasic.objects.filter(
                    exam_id=compare_exam_id,
                    district_name=district_name,
                    select_type=select_type
                ).values('school_name').annotate(
                    student_count=Count('id'),
                    group_distribution=JSONObject(
                        special=Count(
                            'id',
                            filter=Q(total_score__gte=prev_thresholds['special_score'])
                        ),
                        special_margin=Count(
                            'id',
                            filter=Q(
                                total_score__lt=prev_thresholds['special_score'],
                                total_score__gte=prev_thresholds['special_score'] - 10
                            )
                        ),
                        regular=Count(
                            'id',
                            filter=Q(total_score__gte=prev_thresholds['regular_score'])
                        ),
                        regular_margin=Count(
                            'id',
                            filter=Q(
                                total_score__lt=prev_thresholds['regular_score'],
                                total_score__gte=prev_thresholds['regular_score'] - 10
                            )
                        )
                    )
                )

                # 转换为字典方便查找
                prev_data = {
                    school['school_name']: school
                    for school in previous_distribution
                }

                # 添加变化量到当前数据
                current_distribution = list(current_distribution)
                for school in current_distribution:
                    prev_school = prev_data.get(school['school_name'], {})
                    prev_counts = prev_school.get('group_distribution', {})

                    # 计算各群体的变化量
                    changes = {
                        key: school['group_distribution'][key] - prev_counts.get(key, 0)
                        for key in ['special', 'special_margin', 'regular', 'regular_margin']
                    }

                    school['changes'] = changes
                    school['total_change'] = (
                            school['student_count'] -
                            prev_school.get('student_count', 0)
                    )

            return current_distribution

        except Exception as e:
            raise Exception(f"学校分布数据获取失败: {str(e)}")

    def get_subject_analysis(self, exam_id, select_type='理科', district_name='开平市', compare_exam_id=None):
        """获取学科分析数据。"""
        try:
            thresholds = self.get_thresholds(exam_id, select_type)

            # 如果没有指定比较考试，获取上一次考试ID
            if not compare_exam_id:
                previous_exam = ScoreStudentBasic.objects.filter(
                    exam_id__lt=exam_id,
                    select_type=select_type,
                    district_name=district_name
                ).values('exam_id').distinct().order_by('-exam_id').first()

                if previous_exam:
                    compare_exam_id = previous_exam['exam_id']

            print(f"当前考试: {exam_id}")
            print(f"比较考试: {compare_exam_id} ({'用户选择' if compare_exam_id else '默认上一次'})")

            # 定义科目顺序
            if select_type == '理科':
                subjects = [
                    'chinese',  # 语文
                    'math',  # 数学
                    'english',  # 英语
                    'physics',  # 物理
                    'chemistry',  # 化学
                    'biology',  # 生物
                    'geography',  # 地理
                    'politics'  # 政治
                ]
            else:  # 文科
                subjects = [
                    'chinese',  # 语文
                    'math',  # 数学
                    'english',  # 英语
                    'history',  # 历史
                    'geography',  # 地理
                    'politics',  # 政治
                    'chemistry',  # 化学
                    'biology'  # 生物
                ]

            subject_names = {
                'chinese': '语文',
                'math': '数学',
                'english': '英语',
                'physics': '物理',
                'chemistry': '化学',
                'biology': '生物',
                'politics': '政治',
                'history': '历史',
                'geography': '地理'
            }

            # 获取当前考试数据
            current_stats = self._get_exam_stats(
                exam_id, subjects, thresholds, select_type, district_name
            )

            # 获取比较考试数据
            compare_stats = None
            if compare_exam_id:
                compare_thresholds = self.get_thresholds(compare_exam_id, select_type)
                compare_stats = self._get_exam_stats(
                    compare_exam_id, subjects, compare_thresholds, select_type, district_name
                )

                # 计算变化量
                for school in current_stats:
                    school_name = school['school_name']
                    compare_school = next(
                        (s for s in compare_stats if s['school_name'] == school_name),
                        None
                    )

                    if compare_school:
                        # 计算人数变化
                        school['special_count_change'] = (
                                school['special_count'] - compare_school['special_count']
                        )
                        school['regular_count_change'] = (
                                school['regular_count'] - compare_school['regular_count']
                        )

                        # 计算各科目变化
                        for subject in subjects:
                            # 原始分变化
                            school[f'special_{subject}_avg_change'] = (
                                    (school[f'special_{subject}_avg'] or 0) -
                                    (compare_school[f'special_{subject}_avg'] or 0)
                            )
                            school[f'regular_{subject}_avg_change'] = (
                                    (school[f'regular_{subject}_avg'] or 0) -
                                    (compare_school[f'regular_{subject}_avg'] or 0)
                            )

                            # 相对位置变化
                            school[f'special_{subject}_relative_change'] = (
                                    (school[f'special_{subject}_relative'] or 0) -
                                    (compare_school[f'special_{subject}_relative'] or 0)
                            )
                            school[f'regular_{subject}_relative_change'] = (
                                    (school[f'regular_{subject}_relative'] or 0) -
                                    (compare_school[f'regular_{subject}_relative'] or 0)
                            )

            # 扩展调试信息
            print("\n=== 返回数据检查 ===")
            print(f"科目列表: {subjects}")
            print(f"学校统计数据数量: {len(current_stats) if current_stats else 0}")
            if current_stats:
                print("\n第一所学校数据示例:")
                school = current_stats[0]
                print(f"学校名: {school.get('school_name')}")
                print(f"特控群人数: {school.get('special_count')}")
                print(f"本科群人数: {school.get('regular_count')}")
                print("\n各科目成绩:")
                for subject in subjects:
                    print(f"{subject_names[subject]}:")
                    print(f"  特控均分: {school.get(f'special_{subject}_avg')}")
                    print(f"  本科均分: {school.get(f'regular_{subject}_avg')}")
                    print(f"  特控相对位置: {school.get(f'special_{subject}_relative')}")
                    print(f"  本科相对位置: {school.get(f'regular_{subject}_relative')}")

            return {
                'school_stats': current_stats,
                'subjects': subjects,
                'subject_names': subject_names,
                'compare_exam_id': compare_exam_id
            }

        except Exception as e:
            raise Exception(f"学科分析数据获取失败: {str(e)}")

    def _get_exam_stats(self, exam_id, subjects, thresholds, select_type, district_name):
        """获取单次考试的统计数据。"""
        try:
            # 基础统计数据
            school_stats = list(ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                district_name=district_name,
                select_type=select_type
            ).values('school_name').annotate(
                # 特控群统计
                special_count=Count(
                    'id',
                    filter=Q(total_score__gte=thresholds['special_score'])
                ),
                **{f"special_{subject}_avg": Avg(
                    subject,
                    filter=Q(total_score__gte=thresholds['special_score'])
                ) for subject in subjects},
                **{f"special_{subject}_std": StdDev(
                    subject,
                    filter=Q(total_score__gte=thresholds['special_score'])
                ) for subject in subjects},

                # 本科群统计
                regular_count=Count(
                    'id',
                    filter=Q(total_score__gte=thresholds['regular_score'])
                ),
                **{f"regular_{subject}_avg": Avg(
                    subject,
                    filter=Q(total_score__gte=thresholds['regular_score'])
                ) for subject in subjects},
                **{f"regular_{subject}_std": StdDev(
                    subject,
                    filter=Q(total_score__gte=thresholds['regular_score'])
                ) for subject in subjects},

                # 总人数
                student_count=Count('id')
            ).order_by('-regular_count', '-student_count'))

            # 计算相对位置
            queryset = ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                district_name=district_name,
                select_type=select_type
            )

            for subject in subjects:
                # 计算全体考生的均值和标准差
                all_stats = queryset.aggregate(
                    mean=Avg(subject),
                    std=StdDev(subject)
                )
                mean = all_stats['mean'] or 0
                std = all_stats['std'] or 1  # 避免除以0

                # 为每个学校计算相对位置
                for school in school_stats:
                    # 特控群相对位置
                    special_avg = school.get(f'special_{subject}_avg')
                    if special_avg is not None:
                        school[f'special_{subject}_relative'] = (special_avg - mean) / std
                    else:
                        school[f'special_{subject}_relative'] = None

                    # 本科群相对位置
                    regular_avg = school.get(f'regular_{subject}_avg')
                    if regular_avg is not None:
                        school[f'regular_{subject}_relative'] = (regular_avg - mean) / std
                    else:
                        school[f'regular_{subject}_relative'] = None

            # 调试输出
            print("\n=== 相对位置计算结果 ===")
            if school_stats:
                first_school = school_stats[0]
                print(f"第一所学校: {first_school['school_name']}")
                for subject in subjects:
                    print(f"{subject}:")
                    print(f"  特控相对位置: {first_school.get(f'special_{subject}_relative')}")
                    print(f"  本科相对位置: {first_school.get(f'regular_{subject}_relative')}")

            return school_stats

        except Exception as e:
            print(f"_get_exam_stats 错误: {str(e)}")
            raise

    def calculate_zscore(self, scores):
        """计算Z分数。

        Args:
            scores (list): 原始分数列表

        Returns:
            list: Z分数列表
        """
        scores = np.array(scores)
        mean = np.mean(scores)
        std = np.std(scores)
        if std == 0:
            return np.zeros_like(scores)
        return ((scores - mean) / std).tolist()

    def get_warnings(self, exam_id, select_type='理科', district_name='开平市'):
        """获取预警信息。

        Args:
            exam_id (str): 考试ID
            select_type (str): 分科类型，默认为'理科'
            district_name (str): 区域名称，默认为'开平市'

        Returns:
            list: 包含预警信息的列表

        Raises:
            Exception: 当数据查询失败时抛出异常
        """
        try:
            thresholds = self.get_thresholds(exam_id, select_type)

            warnings = []
            records = TrackingRecord.objects.filter(
                exam_id=exam_id,
                score_student_basic__district_name=district_name,
                score_student_basic__select_type=select_type
            ).select_related('score_student_basic').annotate(
                math_score=Cast('subject_scores__math', FloatField()),
                physics_score=Cast('subject_scores__physics', FloatField())
            ).filter(
                Q(weighted_improvement__lt=-10) |
                Q(math_score__isnull=False, physics_score__isnull=False) &
                Q(total_score__gte=thresholds['special_score'] - 10)
            )

            for record in records:
                warning = {
                    'school_name': record.score_student_basic.school_name
                }

                if record.weighted_improvement < -10:
                    warning.update({
                        'warning_type': '成绩下滑',
                        'warning_message': (
                            f"{record.score_student_basic.school_name} - "
                            f"成绩下滑({record.weighted_improvement:.1f})"
                        )
                    })
                elif (record.math_score and record.physics_score and
                      abs(record.math_score - record.physics_score) > 20):
                    warning.update({
                        'warning_type': '学科不均衡',
                        'warning_message': (
                            f"{record.score_student_basic.school_name} - "
                            "数理差异过大"
                        )
                    })

                if warning.get('warning_type'):
                    warnings.append(warning)

            return sorted(
                warnings,
                key=lambda x: (
                    x['warning_type'] != '成绩下滑',
                    x['warning_type'] != '学科不均衡'
                )
            )[:5]

        except Exception as e:
            raise Exception(f"预警信息获取失败: {str(e)}")

    def get(self, request, module_type, exam_id):
        """处理GET请求。

        Args:
            request: HTTP请求对象
            module_type: 模块类型
            exam_id: 考试ID

        Returns:
            渲染后的模板响应或错误JSON响应
        """
        try:
            select_type = request.GET.get('select_type', '理科')
            district_name = request.GET.get('district_name', '开平市')
            compare_exam_id = request.GET.get('compare_exam_id')  # 获取比较的考试ID

            # 获取可选的历史考试列表
            available_exams = ScoreStudentBasic.objects.filter(
                exam_id__lt=exam_id,
                select_type=select_type,
                district_name=district_name
            ).values(
                'exam_id'
            ).distinct().order_by('-exam_id')[:5]  # 获取最近5次考试

            print(f"当前考试: {exam_id}")
            print(f"可比较考试列表: {list(available_exams)}")
            print(f"选择的比较考试: {compare_exam_id}")

            # 如果没有指定比较的考试，使用最近一次
            if not compare_exam_id and available_exams:
                compare_exam_id = available_exams[0]['exam_id']
                print(f"使用默认比较考试: {compare_exam_id}")
            # 获取学科分析数据
            subject_analysis_data = self.get_subject_analysis(
                exam_id,
                select_type,
                district_name,
                compare_exam_id
            )
            context = {
                'module_type': module_type,
                'exam_id': exam_id,
                'select_type': select_type,
                'district_name': district_name,
                'available_exams': available_exams,
                'compare_exam_id': compare_exam_id,
                'group_stats': self.get_group_statistics(
                    exam_id,
                    select_type,
                    district_name,
                    compare_exam_id
                ),
                'school_distribution': self.get_school_distribution(
                    exam_id,
                    select_type,
                    district_name,
                    compare_exam_id
                ),
                'subject_analysis': subject_analysis_data

            }
            print("\n=== 最终 context 数据 ===")
            print(f"subject_analysis 中的学校数: {len(context['subject_analysis']['school_stats'])}")
            print(f"compare_exam_id: {context['compare_exam_id']}")
            return render(request, self.template_name, context)

        except Exception as e:
            error_msg = f"处理请求失败: {str(e)}"
            print(f"错误: {error_msg}")
            print(f"参数: exam_id={exam_id}, select_type={select_type}, "
                  f"district_name={district_name}, compare_exam_id={compare_exam_id}")

            return JsonResponse({
                'error': error_msg,
                'exam_id': exam_id,
                'select_type': select_type,
                'district_name': district_name,
                'compare_exam_id': compare_exam_id
            }, status=500)
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

