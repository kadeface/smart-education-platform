# score_analysis/views/exam_overview.py
from django.shortcuts import render
from django.views.generic import TemplateView
from django.db.models import Max, Min, Avg, Count

import json

from score_analysis.models import ScoreStudentBasic
from score_analysis.models.statistics import ExamLevelStatistics

import logging
logger = logging.getLogger(__name__)

class ExamOverviewView(TemplateView):
   # template_name = 'score_analysis/overview/exam_overview.html'

    def get(self, request, module_type, exam_id):
        try:
            # 获取该考试的所有select_type
            select_types = ExamLevelStatistics.objects.filter(
                exam_id=exam_id
            ).values_list('select_type', flat=True).distinct()

            # 判断是否包含理科或文科
            has_subjects = any(select_type in ['理科', '文科'] for select_type in select_types)

            # 根据不同情况获取不同的数据和使用不同的模板
            if has_subjects:
                context = self.get_context_data_with_subjects(exam_id)
                template_name = 'score_analysis/overview/exam_overview_with_subjects.html'
            else:
                context = self.get_context_data_no_subjects(exam_id)
                template_name = 'score_analysis/overview/exam_overview_no_subjects.html'

            context.update({
                'module_type': module_type,
                'exam_id': exam_id
            })

            return render(request, template_name, context)
        except Exception as e:
            print(f"Error: {str(e)}")
            return render(request, 'score_analysis/client/error.html', {
                'error_message': f'获取统计数据时发生错误: {str(e)}'
            })

    def get_context_data_with_subjects(self, exam_id):
        """获取分科考试的数据"""

        context = {}

        # 1. 获取基础成绩统计数据
        basic_stats = ScoreStudentBasic.objects.filter(
            exam_id=exam_id,
            total_score__isnull=False
        )
        logger.info(f"基础成绩数据数量: {basic_stats.count()}")

        # 2. 获取考试级别数据
        exam_stats = ExamLevelStatistics.objects.filter(exam_id=exam_id)
        logger.info(f"考试统计数据数量: {exam_stats.count()}")

        # 检查是否存在市级数据来判断考试级别
        has_city_data = exam_stats.filter(level_type='city').exists()
        logger.info(f"是否有市级数据: {has_city_data}")


        if has_city_data:
            # 3. 处理市级数据
            city_stats = exam_stats.filter(level_type='city')

            # 理科数据
            science_basic_stats = basic_stats.filter(select_type='理科').aggregate(
                school_count=Count('school_name', distinct=True),
                student_count=Count('student_id'),
                max_score=Max('total_score')
            )
            science_top_school = basic_stats.filter(
                select_type='理科',
                total_score=science_basic_stats['max_score']
            ).values_list('school_name', flat=True).first() or "暂无数据"

            science_stats = city_stats.filter(select_type='理科').first()
            logger.info(f"理科统计数据: {science_stats}")
            context['science'] = self._prepare_stats(
                science_stats,
                science_basic_stats,
                science_top_school
            )
            logger.info(f"处理后的理科数据: {context['science']}")
            # 文科数据
            arts_basic_stats = basic_stats.filter(select_type='文科').aggregate(
                school_count=Count('school_name', distinct=True),
                student_count=Count('student_id'),
                max_score=Max('total_score')
            )
            arts_top_school = basic_stats.filter(
                select_type='文科',
                total_score=arts_basic_stats['max_score']
            ).values_list('school_name', flat=True).first() or "暂无数据"

            arts_stats = city_stats.filter(select_type='文科').first()
            context['arts'] = self._prepare_stats(
                arts_stats,
                arts_basic_stats,
                arts_top_school
            )

        # 4. 处理区县数据
        districts = exam_stats.filter(
            level_type='district'
        ).order_by('district_name', 'select_type')

        if districts.exists():
            context['districts'] = [
                self._prepare_district_stats(stat) for stat in districts
            ]

            # 如果是区县级考试，使用第一个区县的数据作为主要数据
            if not has_city_data:
                district_stats_by_type = {}
                for stat in districts:
                    district_stats_by_type[stat.select_type] = stat

                # 理科数据
                if '理科' in district_stats_by_type:
                    science_basic_stats = basic_stats.filter(
                        select_type='理科',
                        district_name=district_stats_by_type['理科'].district_name
                    ).aggregate(
                        school_count=Count('school_name', distinct=True),
                        student_count=Count('student_id'),
                        max_score=Max('total_score')
                    )
                    science_top_school = basic_stats.filter(
                        select_type='理科',
                        total_score=science_basic_stats['max_score'],
                        district_name=district_stats_by_type['理科'].district_name
                    ).values_list('school_name', flat=True).first() or "暂无数据"

                    context['science'] = self._prepare_stats(
                        district_stats_by_type['理科'],
                        science_basic_stats,
                        science_top_school
                    )

                # 文科数据
                if '文科' in district_stats_by_type:
                    arts_basic_stats = basic_stats.filter(
                        select_type='文科',
                        district_name=district_stats_by_type['文科'].district_name
                    ).aggregate(
                        school_count=Count('school_name', distinct=True),
                        student_count=Count('student_id'),
                        max_score=Max('total_score')
                    )
                    arts_top_school = basic_stats.filter(
                        select_type='文科',
                        total_score=arts_basic_stats['max_score'],
                        district_name=district_stats_by_type['文科'].district_name
                    ).values_list('school_name', flat=True).first() or "暂无数据"

                    context['arts'] = self._prepare_stats(
                        district_stats_by_type['文科'],
                        arts_basic_stats,
                        arts_top_school
                    )

        return context

    def get_context_data_no_subjects(self, exam_id):
        """获取不分科考试的数据"""
        context = {}

        # 获取全市数据
        city_stats = ExamLevelStatistics.objects.filter(
            exam_id=exam_id,
            level_type='city'
        ).first()

        context['total_stats'] = self._prepare_stats(city_stats)

        # 区数据
        districts = ExamLevelStatistics.objects.filter(
            exam_id=exam_id,
            level_type='district'
        ).order_by('district_name')

        context['districts'] = [
            self._prepare_district_stats(stat) for stat in districts
        ]

        return context


    def _prepare_stats(self, stats, basic_stats, top_school):
        """准备统计数据"""
        if not stats:
            return None



        threshold_stats = self.parse_json(stats.threshold_stats) if stats.threshold_stats else {}
        school_distribution = self.parse_json(stats.school_distribution) if stats.school_distribution else {}
        rank_distribution = self.parse_json(stats.rank_distribution) if stats.rank_distribution else {}

        return {
            'school_count': basic_stats['school_count'],
            'student_count': stats.student_count,
            'max_score': round(float(stats.max_score), 2),
            'min_score': round(float(stats.min_score), 2),
            'mean_score': round(float(stats.mean_score), 2),
            'std_dev': round(float(stats.std_dev), 2),
            'top_school': top_school,

            # 各类分数线统计
            'threshold_stats': threshold_stats,

            # 学校分布数据
            'school_stats': school_distribution,

            # 分数分布数据
            'rank_distribution': rank_distribution
        }


    def _prepare_district_stats(self, stats):
        """准备区县统计数据"""
        if not stats:
            return None



        school_data = self.parse_json(stats.school_distribution) if stats.school_distribution else {}
        threshold_data = self.parse_json(stats.threshold_stats) if stats.threshold_stats else {}

        return {
            'district_name': stats.district_name,
            'select_type': stats.select_type,
            'student_count': stats.student_count,
            'max_score': round(float(stats.max_score), 2),
            'min_score': round(float(stats.min_score), 2),
            'mean_score': round(float(stats.mean_score), 2),
            'std_dev': round(float(stats.std_dev), 2),

            # 学校统计数据
            'school_stats': school_data,

            # 录取率统计数据
            'rank_distribution': threshold_data
        }
   # 解析JSON字符串数据，处理可能已经是字典的情况


    def parse_json(self,data):
        if isinstance(data, dict):
            return data
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return {}
        return {}