# score_analysis/services/statistics/statistics_service.py

import json
import logging
from sys import path
from django.contrib import messages
from django.db.models import Subquery, OuterRef
from django.shortcuts import render, redirect
from django.urls import reverse

from score_analysis.models import (
    ScoreRankings,
    BaseExamConfig,
    ScoreStudentBasic
)
from score_analysis.models.statistics import StatisticsExamIndicators,ExamScoreLines
from ..base_statistics import BaseStatisticsService

logger = logging.getLogger(__name__)


class StatisticsViewService:
    """统计数据查看服务"""

    def _get_level_type(self, exam_id):
        """
        根据考试ID获取统计层级信息
        """
        try:
            if 'CITY' in exam_id:
                # 对于市级考试，获取所有区县
                districts = StatisticsExamIndicators.objects.filter(
                    exam_id=exam_id,
                    subject_id='total_score',
                    student_count__gt=0
                ).exclude(
                    level_type='地市级'
                ).values_list('level_type', flat=True).distinct()

                return '地市级', list(districts)
            else:
                # 对于区县级考试
                district = StatisticsExamIndicators.objects.filter(
                    exam_id=exam_id,
                    subject_id='total_score',
                    student_count__gt=0
                ).values_list('level_type', flat=True).first()

                return district, None

        except Exception as e:
            logger.error(f"获取考试层级失败: {str(e)}")
            return None, None

    def _process_summary_data(self, stats):
        """处理综述数据"""
        if not stats:
            return {}

        try:
            # 解析基础数据
            school_count = len(json.loads(stats.school_distribution)) if stats.school_distribution else 0
            thresholds = json.loads(stats.threshold_stats) if stats.threshold_stats else {}

            # 获取第一名学校信息
            top_student = ScoreRankings.objects.filter(
                exam_id=stats.exam_id,
                subject_id='total_score',
                select_type=stats.select_type,
                raw_score=stats.max_score
            ).exclude(
                level_type='地市级'
            ).order_by('-raw_score').first()

            # 处理分数线数据
            score_lines = self._process_score_lines(stats, thresholds)

            # 整理返回数据
            return {
                'school_count': school_count,
                'student_count': stats.student_count,
                'mean_score': round(float(stats.mean_score or 0), 2),
                'max_score': float(stats.max_score or 0),
                'top_school': top_student.school_name if top_student else '未知',
                'score_lines': score_lines
            }

        except Exception as e:
            logger.error(f"处理综述数据失败: {str(e)}")
            return {}

    def _process_score_lines(self, stats, thresholds):
        """处理分数线数据"""
        score_lines = {}
        name_mapping = {
            'C9层': 'c9',
            '985层': '985',
            '211层': '211',
            '双一流层': 'dual_first_class',
            '优分层': 'excellent',
            '本科层': 'undergraduate'
        }

        total_students = stats.student_count or 1

        for display_name, key in name_mapping.items():
            line_data = thresholds.get(display_name, {})
            count = int(line_data.get('count', 0) or 0)
            rate = (count / total_students) * 100 if total_students > 0 else 0

            score_lines[key] = {
                'name': display_name,
                'score': float(line_data.get('line', 0) or 0),
                'count': count,
                'rate': round(rate, 2)
            }

        return score_lines

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        """获取所有有成绩的考试"""
        # 1. 从成绩表获取所有考试ID
        exams_with_scores = list(ScoreStudentBasic.objects.values_list('exam_id', flat=True).distinct())

        # 2. 获取现有的统计记录，并关联考试名称
        # 只获取总分记录，避免重复显示
        existing_stats = StatisticsExamIndicators.objects.filter(
            exam_id__in=exams_with_scores,
            select_type='理科',
            level_type='city',
            subject_id='total_score'  # 只显示总分记录
        ).annotate(
            exam_name=Subquery(
                BaseExamConfig.objects.filter(
                    exam_id=OuterRef('exam_id')
                ).values('exam_name')[:1]
            )
        )

        # 3. 如果没有统计记录，为所有考试创建初始记录
        if not existing_stats.exists():
            stats_to_create = []
            for exam_id in exams_with_scores:
                stats_to_create.append(
                    StatisticsExamIndicators(
                        exam_id=exam_id,
                        select_type='理科',
                        level_type='city',
                        subject_id='total_score'  # 确保新建记录是总分
                    )
                )
            if stats_to_create:
                StatisticsExamIndicators.objects.bulk_create(stats_to_create)
                # 重新查询，包含考试名称
                return StatisticsExamIndicators.objects.filter(
                    exam_id__in=exams_with_scores,
                    select_type='理科',
                    level_type='city',
                    subject_id='total_score'  # 只返回总分记录
                ).annotate(
                    exam_name=Subquery(
                        BaseExamConfig.objects.filter(
                            exam_id=OuterRef('exam_id')
                        ).values('exam_name')[:1]
                    )
                )

        return existing_stats

    def exam_id(self, obj):
        """获取考试名称"""
        return getattr(obj, 'exam_name', obj.exam_id)

    exam_id.short_description = '考试名称'


    def exam_time(self, obj):
        """从考试名称中提取时间"""
        """从考试ID中提取时间"""
        if obj.exam_id and len(obj.exam_id) >= 6:
            year = obj.exam_id[:4]  # 取前4位作为年份
            month = obj.exam_id[4:6]  # 取第5-6位作为月份
            result = f"{year}年{month}月"
            return result
        return ''

    exam_time.short_description = '考试时间'


    def has_statistics(self, obj):
        def has_statistics(self, obj):
            """是否已生成统计"""
            try:
                # 检查是否存在统计数据
                return StatisticsExamIndicators.objects.filter(
                    exam_id=obj.exam_id,
                    subject_id='total_score',
                    student_count__gt=0
                ).exists()
            except Exception as e:
                logger.error(f"检查统计状态失败: {str(e)}")
                return False

    def get_action_button(self, obj):
        """获取操作按钮"""
        try:
            # 检查是否存在有效的统计数据
            has_stats = StatisticsExamIndicators.objects.filter(
                exam_id=obj.exam_id,
                subject_id='total_score',
                student_count__gt=0
            ).exists()

            button_text = "重新统计" if has_stats else "生成统计"

            # 生成统计按钮
            generate_url = reverse(
                'admin:score_analysis_statisticsexamindicators_generate_statistics',
                args=[obj.exam_id]
            )

            buttons = [
                f'<a class="button" style="background-color: #79aec8; padding: 5px 10px; '
                f'color: white; text-decoration: none; border-radius: 4px; margin-right: 5px;" '
                f'href="{generate_url}">{button_text}</a>'
            ]

            if has_stats:
                # 查看结果按钮
                view_url = reverse(
                    'admin:score_analysis_statisticsexamindicators_view_statistics',
                    args=[obj.exam_id]
                )
                buttons.append(
                    f'<a class="button" style="background-color: #417690; padding: 5px 10px; '
                    f'color: white; text-decoration: none; border-radius: 4px;" '
                    f'href="{view_url}">查看结果</a>'
                )

            return mark_safe(''.join(buttons))
        except Exception as e:
            logger.error(f"生成操作按钮失败: {str(e)}")
            return "操作失败"

    get_action_button.short_description = '操作'

    def generate_statistics(self, request, exam_id):
        """生成统计数据"""
        try:
            print(f"开始生成统计数据: exam_id={exam_id}")
            service = BaseStatisticsService()

            # 解析考试ID获取考试级别
            exam_parts = exam_id.split('-')
            if len(exam_parts) < 2:
                raise ValueError(f"无效的考试ID格式: {exam_id}")

            exam_level = exam_parts[1].upper()  # DIST 或 CITY

            # 删除旧的统计数据
            StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                subject_id__isnull=True
            ).delete()

            if exam_level == 'CITY':
                # 市级考试需要生成市级和区县级统计
                # 1. 生成市级统计
                service.generate_all_statistics(exam_id=exam_id, select_type='理科', level_type='city', request=request)
                service.generate_all_statistics(exam_id=exam_id, select_type='文科', level_type='city', request=request)

                # 2. 生成区县级统计
                service.generate_all_statistics(exam_id=exam_id, select_type='理科', level_type='district',
                                                request=request)
                service.generate_all_statistics(exam_id=exam_id, select_type='文科', level_type='district',
                                                request=request)

                messages.success(request, f'考试 {exam_id} 的市级和区县级统计数据已生成')

            elif exam_level == 'DIST':
                # 区县考试只生成区县级统计
                service.generate_all_statistics(exam_id=exam_id, select_type='理科', level_type='district',
                                                request=request)
                service.generate_all_statistics(exam_id=exam_id, select_type='文科', level_type='district',
                                                request=request)

                messages.success(request, f'考试 {exam_id} 的区县级统计数据已生成')

            else:
                raise ValueError(f"未知的考试级别: {exam_level}")
            return redirect('admin:score_analysis_statisticsexamindicators_view_statistics',
                          exam_id=exam_id)


        except Exception as e:
            print(f"生成统计失败: {str(e)}")
            messages.error(request, f'考试 {exam_id} 统计数据生成失败: {str(e)}')
            return redirect('admin:score_analysis_statisticsexamindicators_changelist')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            # 生成统计的URL
            path('generate-statistics/<str:exam_id>/',
                 self.admin_site.admin_view(self.generate_statistics),
                 name='score_analysis_statisticsexamindicators_generate_statistics'),

            # 查看统计结果的URL
            path('view-statistics/<str:exam_id>/',
                 self.admin_site.admin_view(self.view_statistics),
                 name='score_analysis_statisticsexamindicators_view_statistics'),
        ]
        return custom_urls + urls

    def view_statistics(self, request, exam_id):
        """查看统计结果页面"""
        try:
            # 1. 获取考试层级信息
            level_type, districts = self._get_level_type(exam_id)
            logger.info(f"考试 {exam_id} 的统计层级为: {level_type}, 包含区县: {districts}")

            if not level_type:
                raise ValueError(f"无法确定考试 {exam_id} 的统计层级")

            # 2. 获取理科和文科的统计数据
            science_stats = StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                select_type='理科',
                subject_id='total_score',
                level_type=level_type,
                student_count__gt=0
            ).first()

            arts_stats = StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                select_type='文科',
                subject_id='total_score',
                level_type=level_type,
                student_count__gt=0
            ).first()

            # 3. 获取考试名称
            exam_name = BaseExamConfig.objects.filter(exam_id=exam_id).values_list('exam_name', flat=True).first()

            # 4. 处理各类统计数据
            context = {
                'title': f'{exam_name} - 统计结果',
                'exam_id': exam_id,
                'exam_name': exam_name,
                'level_type': level_type,

                # 统计数据
                'science_summary': self._process_summary_data(science_stats),
                'arts_summary': self._process_summary_data(arts_stats),
                'science_score_lines': self._score_line_distribution(science_stats),
                'arts_score_lines': self._score_line_distribution(arts_stats),
                'science_rankings': dict(sorted(
                    self._process_rank_distribution(science_stats).items(),
                    key=lambda x: x[1]['top_10'],
                    reverse=True
                )) if science_stats else {},
                'arts_rankings': dict(sorted(
                    self._process_rank_distribution(arts_stats).items(),
                    key=lambda x: x[1]['top_10'],
                    reverse=True
                )) if arts_stats else {},
                'science_quartiles': self._process_quartile_analysis(science_stats, 'science'),
                'arts_quartiles': self._process_quartile_analysis(arts_stats, 'arts'),
                'science_school_means': self._process_school_subject_means(science_stats, 'science'),
                'arts_school_means': self._process_school_subject_means(arts_stats, 'arts'),

                **self.admin_site.each_context(request),
            }

            # 5. 如果是地市级考试，获取区县数据
            if level_type == '地市级' and districts:
                district_data = {}
                for district in districts:
                    district_stats_science = StatisticsExamIndicators.objects.filter(
                        exam_id=exam_id,
                        select_type='理科',
                        subject_id='total_score',
                        level_type=district,
                        student_count__gt=0
                    ).first()

                    district_stats_arts = StatisticsExamIndicators.objects.filter(
                        exam_id=exam_id,
                        select_type='文科',
                        subject_id='total_score',
                        level_type=district,
                        student_count__gt=0
                    ).first()

                    district_data[district] = {
                        'science': self._process_summary_data(district_stats_science),
                        'arts': self._process_summary_data(district_stats_arts)
                    }

                context['district_data'] = district_data

            return render(
                request,
                'admin/score_analysis/statisticsexamindicators/generate_stats.html',
                context
            )

        except Exception as e:
            logger.error(f"获取统计数据失败: {str(e)}")
            messages.error(request, f'获取统计数据失败: {str(e)}')
            return redirect('admin:score_analysis_statisticsexamindicators_changelist')
    #获取考试的类型（江门市统考或者开平市统考）
    def _get_exam_statistics(self, exam_id):
        """获取考试统计数据"""

        # 判断考试类型并返回对应的level_type
        if 'CITY' in exam_id:
            return 'city'  # 地市级统考
        else:
            return '开平市'  # 默认为区县级别（开平市）
    #获取考试的类型（江门市统考或者区县市统考）
    def _get_level_type(self, exam_id):
        """
        根据考试ID获取统计层级信息

        Args:
            exam_id: str, 考试ID (例如: JM-CITY-2023-1)

        Returns:
            tuple: (level_type, districts)
                - level_type: str, '地市级' 或 具体区县名
                - districts: list, 如果是地市级考试则返回所有区县列表，否则返回None
        """
        logger.info(f"开始确定考试 {exam_id} 的统计层级")

        try:
            if 'CITY' in exam_id:
                # 对于市级考试，获取所有区县
                districts = StatisticsExamIndicators.objects.filter(
                    exam_id=exam_id,
                    subject_id='total_score',
                    student_count__gt=0
                ).exclude(
                    level_type='地市级'
                ).values_list('level_type', flat=True).distinct()

                return '地市级', list(districts)
            else:
                # 对于区县级考试
                district = StatisticsExamIndicators.objects.filter(
                    exam_id=exam_id,
                    subject_id='total_score',
                    student_count__gt=0
                ).values_list('level_type', flat=True).first()

                if district:
                    logger.info(f"区县级考试: {district}")
                    return district, None
                else:
                    logger.error(f"未找到考试 {exam_id} 的统计记录")
                    return None, None

        except Exception as e:
            logger.error(f"获取考试层级失败: {str(e)}")
            return None, None
        #综述数据

    def _process_summary_data(self, stats):
        """
        处理综述数据，生成完整的统计信息
        """
        if not stats:
            logger.warning("没有找到统计数据")
            return {}

        try:
            # 1. 解析基础数据
            school_count = len(json.loads(stats.school_distribution)) if stats.school_distribution else 0
            thresholds = json.loads(stats.threshold_stats) if stats.threshold_stats else {}

            # 2. 获取第一名学校信息
            if stats.level_type == '地市级':
                top_student = ScoreRankings.objects.filter(
                    exam_id=stats.exam_id,
                    subject_id='total_score',
                    select_type=stats.select_type,
                    raw_score=stats.max_score
                ).exclude(
                    level_type='地市级'
                ).order_by('-raw_score').first()
            else:
                top_student = ScoreRankings.objects.filter(
                    exam_id=stats.exam_id,
                    subject_id='total_score',
                    select_type=stats.select_type,
                    level_type=stats.level_type
                ).order_by('-raw_score').first()

            # 3. 处理分数线数据
            score_lines = {}
            name_mapping = {
                'C9层': 'c9',
                '985层': '985',
                '211层': '211',
                '双一流层': 'dual_first_class',
                '优分层': 'excellent',
                '本科层': 'undergraduate'
            }

            # 获取总人数，用于计算比率
            total_students = stats.student_count or 1  # 避免除以0

            for display_name, key in name_mapping.items():
                line_data = thresholds.get(display_name, {})
                count = int(line_data.get('count', 0) or 0)
                # 使用总人数计算比率
                rate = (count / total_students) * 100 if total_students > 0 else 0

                score_lines[key] = {
                    'name': display_name,
                    'score': float(line_data.get('line', 0) or 0),
                    'count': count,
                    'rate': round(rate, 2)  # 四舍五入到2位小数
                }

                # 添加日志以检查计算过程
                logger.info(f"{display_name} - 人数: {count}, 总人数: {total_students}, 比率: {rate}%")

            # 4. 整理返回数据
            summary_data = {
                'school_count': school_count,
                'student_count': total_students,
                'mean_score': round(float(stats.mean_score or 0), 2),
                'max_score': float(stats.max_score or 0),
                'top_school': top_student.school_name if top_student else '未知',
                'score_lines': score_lines
            }

            logger.info(f"成功处理统计数据: 学校数={school_count}, 学生数={total_students}, "
                        f"平均分={summary_data['mean_score']}, 最高分={stats.max_score}, "
                        f"第一名学校={summary_data['top_school']}")

            return summary_data

        except Exception as e:
            logger.error(f"处理综述数据失败: {str(e)}")
            logger.exception(e)
            return {}
    #区县学校分数线分布情况
    def _process_school_distribution(self, school_distribution_json):
        """处理学校分布数据"""
        if not school_distribution_json:
            return {
                'school_count': 0,
                'student_count': 0,
                'mean_score': 0,
                'max_score': 0,
                'top_school': "暂无数据"
            }

        # 解析JSON数据
        schools_data = json.loads(school_distribution_json) if isinstance(school_distribution_json,
                                                                          str) else school_distribution_json

        # 计算基础统计数据
        total_students = 0
        weighted_sum = 0
        max_score = 0
        top_school = "暂无数据"

        for school, data in schools_data.items():
            school_count = data['count']
            total_students += school_count
            weighted_sum += data['mean'] * school_count

            if data['max_score'] > max_score:
                max_score = data['max_score']
                top_school = school

        return {
            'school_count': len(schools_data),
            'student_count': total_students,
            'mean_score': round(weighted_sum / total_students, 2) if total_students > 0 else 0,
            'max_score': max_score,
            'top_school': top_school
        }
    #分数线达线情况
    def _score_line_distribution(self, stats_obj):
        """处理分数线分布数据"""
        if not stats_obj or not stats_obj.threshold_stats:
            return {}

        try:
            thresholds = json.loads(stats_obj.threshold_stats)
            # 按照line值从高到低排序
            sorted_thresholds = dict(sorted(
                thresholds.items(),
                key=lambda x: float(x[1].get('line', 0)),
                reverse=True
            ))
            return sorted_thresholds
        except Exception as e:
            logger.error(f"解析threshold_stats失败: {str(e)}")
            return {}
    #各校的排名分布
    def _process_rank_distribution(self, stats):
        """处理排名分布数据
        Args:
            stats: StatisticsExamIndicators实例
        Returns:
            dict: {
                '学校A': {'top_10': 5, 'top_20': 8, 'top_50': 10, ...},
                '学校B': {'top_10': 0, 'top_20': 0, 'top_50': 2, ...},  # 没有的排名补0
            }
        """
        try:
            # 检查数据是否存在
            if not stats or not stats.rank_distribution:
                logger.warning("没有排名分布数据")
                return {}

            # 解析JSON数据
            rank_data = json.loads(stats.rank_distribution)

            # 获取school_rankings数据
            school_rankings = rank_data.get('school_rankings', {})

            # 定义所有需要的排名范围
            rank_ranges = ['top_10', 'top_20', 'top_50', 'top_100',
                           'top_200', 'top_500', 'top_1250']

            # 处理每个学校的数据，确保所有排名范围都存在
            processed_rankings = {}
            for school, rankings in school_rankings.items():
                processed_rankings[school] = {
                    rank_range: rankings.get(rank_range, 0)
                    for rank_range in rank_ranges
                }

            # 按top_10人数排序
            sorted_data = dict(sorted(
                processed_rankings.items(),
                key=lambda x: x[1]['top_10'],
                reverse=True
            ))

            return sorted_data

        except Exception as e:
            logger.error(f"处理排名分布数据失败: {str(e)}")
            return {}
    def _process_quartile_analysis(self, stats, subject_type='science'):
        """处理四分位分析数据"""
        if not stats:
            return {}

        # 定义所有需要分析的科目
        base_subjects = {
            'total_score': '总分',
            'chinese': '语文',
            'math': '数学',
            'english': '英语',
            'chemistry': '化学',
            'biology': '生物',
            'politics': '政治',
            'geography': '地理'
        }

        # 根据文理科添加特定科目
        if subject_type == 'science':
            base_subjects['physics'] = '物理'
        elif subject_type == 'arts':
            base_subjects['history'] = '历史'

        quartile_data = {}

        # 获取每个科目的统计数据
        for subject_code, subject_name in base_subjects.items():
            subject_stats = StatisticsExamIndicators.objects.filter(
                exam_id=stats.exam_id,
                select_type=stats.select_type,
                subject_id=subject_code,
                student_count__gt=0
            ).first()

            if subject_stats:
                quartile_data[subject_name] = {
                    'mean': subject_stats.mean_score,
                    'max': subject_stats.max_score,
                    'q80': subject_stats.q80_score,
                    'median': subject_stats.median_score,
                    'q20': subject_stats.q20_score,
                    'q10': subject_stats.q10_score
                }

        return quartile_data
    #各校的平均分列表
    def _process_school_subject_means(self, stats, exam_type):
        """处理各校各科平均分数据"""
        try:
            if not stats:
                return {'subjects': [], 'schools': []}

            exam_id = stats.exam_id
            select_type = '理科' if exam_type == 'science' else '文科'
            level_type = stats.level_type

            # 获取所有科目的统计数据
            all_stats = StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                select_type=select_type,
                level_type=level_type
            )

            # 打印调试信息
           # logger.info(f"处理{select_type}各校各科平均分数据:")
           # logger.info(f"找到 {all_stats.count()} 个科目的统计数据")

            # 准备数据结构
            schools_data = {}
            subjects_order = []

            # 处理每个科目的数据
            for stat in all_stats:
                subject_name = stat.subject.subject_name
                subjects_order.append(subject_name)

                # 打印当前处理的科目
             #   logger.info(f"处理科目: {subject_name}")

                # 解析school_distribution JSON数据
                try:
                    school_dist = json.loads(stat.school_distribution)
                    logger.info(f"科目 {subject_name} 的学校分布数据: {school_dist}")
                except (json.JSONDecodeError, AttributeError) as e:
                    logger.error(f"解析科目 {subject_name} 的school_distribution失败: {e}")
                    continue

                # 整理每个学校的数据
                for school_name, school_stats in school_dist.items():
                    if school_name not in schools_data:
                        schools_data[school_name] = {
                            'school_name': school_name,
                            'subjects': {}
                        }

                    # 添加该科目的统计数据
                    schools_data[school_name]['subjects'][subject_name] = {
                        'count': school_stats['count'],
                        'mean': school_stats['mean'],
                        'std_dev': school_stats.get('std_dev', 0)
                    }

            # 转换为列表并按总分平均分排序
            schools_list = list(schools_data.values())
            schools_list.sort(
                key=lambda x: x['subjects'].get('总分', {}).get('mean', 0),
                reverse=True
            )

            # 打印最终的数据结构
           # logger.info(f"最终数据结构:")
           # logger.info(f"科目顺序: {subjects_order}")
            #logger.info(f"学校数据示例: {schools_list[0] if schools_list else 'No schools'}")

            return {
                'subjects': subjects_order,
                'schools': schools_list
            }

        except Exception as e:
            logger.error(f"处理学校科目平均分失败: exam_type={exam_type}, error={str(e)}")
            logger.exception("详细错误信息:")
            return {'subjects': [], 'schools': []}


    def _prepare_subject_data(self, stats, score_lines, select_type):
        """准备学科统计数据"""
        if not stats:
            return {}

        # 1. 获取最高分学校
        school_distribution = stats.school_distribution or {}
        top_school = "暂无数据"
        if school_distribution:
            top_scores = sorted(
                [(school, data.get('max_score', 0))
                 for school, data in school_distribution.items()],
                key=lambda x: x[1],
                reverse=True
            )
            if top_scores:
                top_school = top_scores[0][0]

        # 2. 准备基础数据
        data = {
            # 基本信息 - 直接使用数据库字段
            'school_count': len(school_distribution),
            'student_count': stats.student_count,
            'mean_score': float(stats.mean_score) if stats.mean_score else 0,
            'max_score': float(stats.max_score) if stats.max_score else 0,
            'min_score': float(stats.min_score) if stats.min_score else 0,
            'std_dev': float(stats.std_dev) if stats.std_dev else 0,
            'top_school': top_school,

            # 分数线和上线数据
            'excellent_rate': float(stats.excellent_rate) if stats.excellent_rate else 0,
            'pass_rate': float(stats.pass_rate) if stats.pass_rate else 0,
            'low_score_rate': float(stats.low_score_rate) if stats.low_score_rate else 0,
        }

        # 添加分数线数据
        for line_type, score in score_lines.items():
            data[f'{line_type}'] = score
            if stats.threshold_stats and line_type in stats.threshold_stats:
                data[f'{line_type}_count'] = stats.threshold_stats[line_type].get('count', 0)
                data[f'{line_type}_rate'] = stats.threshold_stats[line_type].get('rate', 0)

        # 3. 处理学校分布数据
        school_stats = []
        for school_name, school_data in school_distribution.items():
            school_info = {
                'name': school_name,
                'student_count': school_data.get('student_count', 0),
                'max_score': school_data.get('max_score', 0),
                'min_score': school_data.get('min_score', 0),
                'mean_score': school_data.get('mean_score', 0),
                'mean_rank': school_data.get('mean_rank', 0),
            }

            # 添加各分数线上线数据
            threshold_stats = school_data.get('threshold_stats', {})
            for line_type in score_lines.keys():
                line_stats = threshold_stats.get(line_type, {})
                school_info[f'{line_type}_count'] = line_stats.get('count', 0)
                school_info[f'{line_type}_rate'] = line_stats.get('rate', 0)

            school_stats.append(school_info)

        # 按平均分排序
        school_stats.sort(key=lambda x: x['mean_score'], reverse=True)
        data['school_stats'] = school_stats

        # 4. 处理排名分布数据
        rank_stats = {
            'thresholds': {},
            'total': {},
            'schools': {}
        }

        # 处理各个排名段的分布
        rank_fields = {
            'top10': 'top_10_distribution',
            'top20': 'top_20_distribution',
            'top50': 'top_50_distribution',
            'top100': 'top_100_distribution',
            'top200': 'top_200_distribution',
            'top500': 'top_500_distribution',
            'top1250': 'top_1250_distribution'
        }

        for rank_key, field_name in rank_fields.items():
            distribution = getattr(stats, field_name) or {}
            if distribution:
                rank_stats['thresholds'][rank_key] = distribution.get('min_score', 0)
                rank_stats['total'][rank_key] = distribution.get('count', 0)

        data['rank_stats'] = rank_stats

        # 5. 处理四分位数据
        data.update({
            'q80_score': float(stats.q80_score) if stats.q80_score else 0,
            'median_score': float(stats.median_score) if stats.median_score else 0,
            'q20_score': float(stats.q20_score) if stats.q20_score else 0,
            'q10_score': float(stats.q10_score) if stats.q10_score else 0,
        })

        return data
    # 新增：查看统计结果的方法
    def statistics_result(self, request, exam_id):
        """查看统计结果"""
        try:
            # 1. 获取统计数据
            print(f"正在查找考试ID: {exam_id} 的统计数据")  # 调试信息

            stats_list = StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                subject_id='total_score'
            )

            print(f"找到的统计数据数量: {stats_list.count()}")  # 调试信息

            if not stats_list.exists():
                messages.error(request, f'未找到考试 {exam_id} 的统计数据')
                return redirect('admin:score_analysis_statisticsexamindicators_changelist')

            # 分别获取理科和文科的统计数据
            science_stats = stats_list.filter(select_type='理科').first()
            arts_stats = stats_list.filter(select_type='文科').first()

            print(f"理科统计数据: {science_stats}")  # 调试信息
            print(f"文科统计数据: {arts_stats}")  # 调试信息

            # 获取分数线数据
            score_lines = self.get_score_lines(exam_id)
            print(f"分数线数据: {score_lines}")  # 调试信息

            # 2. 准备上下文数据
            context = {
                'exam_id': exam_id,
                'title': f'考试 {exam_id} 统计结果',
                'science_data': self._prepare_subject_data(
                    science_stats,
                    score_lines.get('理科', {}),
                    '理科'
                ) if science_stats else None,
                'arts_data': self._prepare_subject_data(
                    arts_stats,
                    score_lines.get('文科', {}),
                    '文科'
                ) if arts_stats else None,
                **self.admin_site.each_context(request),
            }

            # 3. 渲染结果页面
            return render(
                request,
                'admin/score_analysis/statisticsexamindicators/generate_stats.html',
                context
            )

        except Exception as e:
            logger.error(f"查看统计结果失败: {str(e)}")
            print(f"错误详情: {str(e)}")  # 调试信息
            messages.error(request, f'查看统计结果失败: {str(e)}')
            return redirect('admin:score_analysis_statisticsexamindicators_changelist')

    def get_score_lines(self, exam_id):
        """从数据库获取分数线数据"""
        try:
            print(f"正在获取考试ID: {exam_id} 的分数线数据")  # 调试信息

            # 获取所有分数线数据
            lines = ExamScoreLines.objects.filter(exam_id=exam_id)
            print(f"找到的分数线数据数量: {lines.count()}")  # 调试信息

            # 初始化默认分数线数据结构
            score_lines = {
                '理科': {
                    'qb_line': 0,
                    '985_line': 0,
                    '211_line': 0,
                    'tk_line': 0,
                    'bk_line': 0,
                    'zk_line': 0
                },
                '文科': {
                    'qb_line': 0,
                    '985_line': 0,
                    '211_line': 0,
                    'tk_line': 0,
                    'bk_line': 0,
                    'zk_line': 0
                }
            }

            # 如果有数据，更新默认值
            if lines.exists():
                # 转换分数线类型名称为代码中使用的键名
                line_type_map = {
                    'C9层': 'qb_line',
                    '985层': '985_line',
                    '211层': '211_line',
                    '双一流层': 'tk_line',
                    '本科层': 'bk_line',
                    '优分层': 'zk_line'
                }

                # 更新分数线数据
                for line in lines:
                    key = line_type_map.get(line.line_type)
                    if key and line.select_type in score_lines:
                        score_lines[line.select_type][key] = float(line.score)
                        print(f"更新分数线: {line.select_type} - {line.line_type} - {line.score}")  # 调试信息

            print(f"最终分数线数据: {score_lines}")  # 调试信息
            return score_lines

        except Exception as e:
            logger.error(f"获取分数线数据失败: {str(e)}")
            print(f"获取分数线数据出错: {str(e)}")  # 调试信息

            # 返回默认值
            return {
                '理科': {
                    'qb_line': 0,
                    '985_line': 0,
                    '211_line': 0,
                    'tk_line': 0,
                    'bk_line': 0,
                    'zk_line': 0
                },
                '文科': {
                    'qb_line': 0,
                    '985_line': 0,
                    '211_line': 0,
                    'tk_line': 0,
                    'bk_line': 0,
                    'zk_line': 0
                }
            }

    # ... 其他方法从 admin 中复制过来 ...