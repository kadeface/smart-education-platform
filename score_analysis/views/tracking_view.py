# views/trackingview.py

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.db.models import Avg, Count, Max, Min

from score_processor.models import StudentMapping, BaseExamConfig
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

