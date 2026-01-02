# score_analysis/views/value_added_view.py

from score_processor.models import BaseSchoolInfo  # 使用已有的模型
from django.http import JsonResponse
from django.db.models import Count, Q
from ..models import BaseExamConfig
from django.views.generic import TemplateView
import json
import pandas as pd
from ..services.value_added_service import ScoreAnalysisForValueAddService

import logging
logger = logging.getLogger('value_added_service')


class ValueAddedHomeView(TemplateView):
    """增值评价首页视图"""
    template_name = 'score_analysis/value_add/value_added_home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        school_levels = {
            'H': {
                'name': '高中',
                'stats': self.get_level_statistics('H')
            },
            'M': {
                'name': '初中',
                'stats': self.get_level_statistics('M')
            },
            'P': {
                'name': '小学',
                'stats': self.get_level_statistics('P')
            }
        }

        context['school_levels'] = school_levels
        return context

    def get_level_statistics(self, level_code):
        """
        获取学段统计信息

        Args:
            level_code: 学段代码 (H/M/P)

        Returns:
            dict: 包含学校总数和各类型学校统计的字典
        """
        # 获取该学段的学校类型统计
        type_stats = BaseSchoolInfo.objects.filter(
            school_level=level_code
        ).values(
            'school_type'
        ).annotate(
            type_count=Count('school_id')
        ).order_by('school_type')

        # 计算总学校数
        total_schools = sum(stat['type_count'] for stat in type_stats)

        # 处理统计结果
        school_types = {}
        for stat in type_stats:
            school_type = stat['school_type'] or '未分类'  # 处理空值
            school_types[school_type] = {
                'count': stat['type_count'],
                'percentage': round((stat['type_count'] / total_schools * 100), 1) if total_schools > 0 else 0
            }

        return {
            'school_count': total_schools,
            'school_types': school_types
        }



class ValueAddedDetailView(TemplateView):
    """增值分析详情视图"""

    template_name = 'score_analysis/value_add/value_added_detail.html'

    def post(self, request, *args, **kwargs):
        """处理POST请求"""
        try:
            selected_exams = request.POST.getlist('selected_exams[]')
            if len(selected_exams) < 2:
                return JsonResponse({
                    'status': 'error',
                    'message': '请至少选择两次考试'
                })

            service = ScoreAnalysisForValueAddService(selected_exams)
            service.prepare_data()
            t_scores_df = service.t_scores_df  # 获取T分数据DataFrame

            # 获取所有唯一的学科及其名称
            subjects_info = t_scores_df[['subject', 'subject_name']].drop_duplicates().to_dict('records')
            logger.info(f"分析的学科: {subjects_info}")

            # 1. 生成区域整体分析结果
            analysis_results = {
                'core_metrics': self._get_core_metrics(t_scores_df),
                'trend_data': self._get_trend_data(t_scores_df),
                'subject_analysis': self._get_subject_analysis(t_scores_df),
            }

            # 2. 添加学校各学科增值对比分析
            schools_comparison = self._get_schools_subject_analysis(t_scores_df)
            # 3. 为每个学校添加分层分析数据
            for school in schools_comparison:
                school_name = school['school_name']
                logger.info(f"处理学校数据: {school_name}")

                # 获取该学校的数据
                school_df = t_scores_df[t_scores_df['school_name'] == school_name]

                if school_df.empty:
                    logger.warning(f"学校 {school_name} 没有找到相关数据")
                    continue

                # 对每个学科进行分层分析
                for subject_info in subjects_info:
                    subject_code = subject_info['subject']
                    subject_name = subject_info['subject_name']

                    subject_df = school_df[school_df['subject'] == subject_code]

                    if not subject_df.empty:
                        logger.info(f"分析学校 {school_name} 的 {subject_name} 学科数据")
                        # 计算分层统计数据
                        level_analysis = self._calculate_level_statistics(subject_df, subject_code)
                        # 将分层分析结果添加到学校数据中
                        school[f'{subject_code}_level_analysis'] = level_analysis
                    else:
                        logger.warning(f"学校 {school_name} 的 {subject_name} 学科没有数据")

            analysis_results['schools_comparison'] = schools_comparison

            # 添加学科信息到返回结果中，方便前端使用
            analysis_results['subjects'] = subjects_info

            return JsonResponse({
                'status': 'success',
                'data': analysis_results
            })

        except Exception as e:
            logger.error(f"分析处理失败: {str(e)}")
            logger.exception(e)
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

    def get_context_data(self, **kwargs):
        """获取上下文数据"""
        context = super().get_context_data(**kwargs)
        school_level = self.kwargs.get('school_level', 'H').upper()

        # 获取对应学段的考试列表
        exam_list = self._get_exam_list(school_level)

        context.update({
            'exam_list': json.dumps(exam_list),
            'school_level': school_level,
            'school_level_display': self._get_school_level_display(school_level),
            'show_result': False
        })

        return context

    def _format_core_metrics(self, analysis_results):
        """格式化核心指标数据"""
        progress_analysis = analysis_results['progress_analysis']
        city_stats = analysis_results['city_stats']

        # 计算整体增值率
        value_added_rate = self._calculate_overall_value_add_rate(progress_analysis)

        return {
            'value_added_rate': value_added_rate,
            'quality_score': self._calculate_quality_score(progress_analysis),
            'improvement_ratio': self._calculate_improvement_ratio(progress_analysis)
        }

    def _format_trend_data(self, analysis_results):
        """格式化趋势数据"""
        t_scores = pd.DataFrame(analysis_results['t_scores'])

        # 按考试ID分组计算平均T分
        trend_data = t_scores.groupby('exam_id')['t_score'].mean().reset_index()

        return {
            'labels': trend_data['exam_id'].tolist(),
            'values': trend_data['t_score'].tolist()
        }

    def _format_subject_analysis(self, analysis_results):
        """格式化学科分析数据"""
        t_scores = pd.DataFrame(analysis_results['t_scores'])
        progress_analysis = analysis_results['progress_analysis']

        # 准备雷达图数据
        subjects = t_scores['subject_name'].unique()
        subject_means = t_scores.groupby('subject_name')['t_score'].mean()

        radar_data = {
            'indicators': subjects.tolist(),
            'values': subject_means.tolist()
        }

        # 准备详细表格数据
        detailed_table = []
        for subject in subjects:
            subject_progress = self._get_subject_progress(subject, progress_analysis)
            detailed_table.append({
                'subject': subject,
                'improvement': subject_progress['improvement_rate'],
                'pattern': subject_progress['pattern'],
                'progress_rate': subject_progress['progress_rate']
            })

        return {
            'radar_data': radar_data,
            'pattern_distribution': self._get_pattern_distribution(detailed_table),
            'detailed_table': detailed_table
        }

    def _get_school_level_display(self, school_level):
        """获取学段类型显示名称"""
        return {
            'H': '高中',
            'M': '初中',
            'P': '小学'
        }.get(school_level, '高中')

    def _get_exam_list(self, school_level):
        """
        获取考试列表

        Args:
            school_level (str): 学段类型，'H'(高中)/'M'(初中)/'P'(小学)

        Returns:
            list: 包含考试信息的字典列表
        """
        try:
            print(f"正在获取{school_level}学段的考试列表")  # 调试信息

            # 构建查询条件
            exam_pattern = f'-{school_level}-'

            # 获取已发布的考试
            exams = BaseExamConfig.objects.filter(
                Q(status='published') &
                Q(exam_id__contains=exam_pattern)
            ).order_by('-exam_date')

            print(f"SQL查询: {exams.query}")  # 打印SQL查询语句
            print(f"找到的考试数量: {exams.count()}")  # 打印找到的考试数量

            exam_list = []
            for exam in exams:
                # 获取考试级别显示名称
                exam_level_display = {
                    'CITY': '市级',
                    'DIST': '区级',
                    'SCHO': '校级',
                }.get(exam.exam_level, '')

                # 获取学期显示名称
                semester_map = {
                    # 高中学期
                    'H1-1': '高一上',
                    'H1-2': '高一下',
                    'H2-1': '高二上',
                    'H2-2': '高二下',
                    'H3-1': '高三上',
                    'H3-2': '高三下',
                    # 初中学期
                    'M1-1': '初一上',
                    'M1-2': '初一下',
                    'M2-1': '初二上',
                    'M2-2': '初二下',
                    'M3-1': '初三上',
                    'M3-2': '初三下',
                    # 小学学期
                    'P5-1': '五年级上',
                    'P5-2': '五年级下',
                    'P6-1': '六年级上',
                    'P6-2': '六年级下',
                }
                semester_display = semester_map.get(exam.semester, '')

                # 格式化考试名称
                exam_name = (f"{exam.exam_date.strftime('%Y年%m月')} "
                             f"{exam_level_display}{exam.exam_name} "
                             f"({semester_display})")

                exam_list.append({
                    'id': exam.exam_id,
                    'name': exam_name,
                    'date': exam.exam_date.strftime('%Y-%m-%d'),
                    'type': exam.exam_type,
                    'level': exam.exam_level,
                    'semester': exam.semester,
                    'is_divided': exam.is_divided_exam,
                    'grade_level': exam.grade_level
                })

            return exam_list

        except Exception as e:
            print(f"获取考试列表错误: {str(e)}")  # 打印错误信息
            return []


    def get_analysis_results(self, t_scores_df):
        """
        获取分析结果。

        Args:
            t_scores_df: T分数据DataFrame

        Returns:
            dict: 包含所有分析结果的字典
        """
        try:
            # 计算整体增值率
            value_added_rate = self._calculate_overall_value_add_rate(t_scores_df)

            # 计算教学质量评分
            quality_score = self._calculate_quality_score(t_scores_df)

            # 计算进步学生比例
            improvement_ratio = self._calculate_improvement_ratio(t_scores_df)

            # 获取趋势数据
            trend_data = self._get_trend_data(t_scores_df)

            # 获取学科分析数据
            subject_analysis = self._get_subject_analysis(t_scores_df)

            return {
                'value_added_rate': value_added_rate,
                'quality_score': quality_score,
                'improvement_ratio': improvement_ratio,
                'trend_data': trend_data,
                'subject_analysis': subject_analysis
            }

        except Exception as e:
            logger.error(f"获取分析结果失败: {str(e)}")
            raise

    def _calculate_overall_value_add_rate(self, df):
        """计算整体增值率"""
        try:
            if df.empty:
                return 0

            # 计算最后一次考试和第一次考试的平均T分差值
            exams = sorted(df['exam_id'].unique())
            if len(exams) < 2:
                return 0

            first_exam = df[df['exam_id'] == exams[0]]['t_score'].mean()
            last_exam = df[df['exam_id'] == exams[-1]]['t_score'].mean()

            return float(last_exam - first_exam)

        except Exception as e:
            logger.error(f"计算整体增值率失败: {str(e)}")
            return 0

    def _calculate_quality_score(self, df):
        """计算教学质量评分"""
        try:
            if df.empty:
                return 0

            # 基于最后一次考试的T分计算质量评分
            last_exam = df['exam_id'].max()
            last_scores = df[df['exam_id'] == last_exam]['t_score']

            # 将T分转换为百分制
            quality_score = (last_scores.mean() - 50) * 2 + 70

            return float(min(max(quality_score, 0), 100))

        except Exception as e:
            logger.error(f"计算教学质量评分失败: {str(e)}")
            return 0

    def _calculate_improvement_ratio(self, df):
        """计算进步学生比例"""
        try:
            if df.empty:
                return 0

            exams = sorted(df['exam_id'].unique())
            if len(exams) < 2:
                return 0

            # 计算每个学生的T分变化
            first_scores = df[df['exam_id'] == exams[0]].set_index('student_id')['t_score']
            last_scores = df[df['exam_id'] == exams[-1]].set_index('student_id')['t_score']

            # 计算进步的学生比例
            improved = sum((last_scores - first_scores) > 0)
            total = len(first_scores)

            return float(improved / total * 100) if total > 0 else 0

        except Exception as e:
            logger.error(f"计算进步学生比例失败: {str(e)}")
            return 0
    def _get_core_metrics(self, df):
        """获取核心指标"""
        try:
            if not isinstance(df, pd.DataFrame):
                return {
                    'value_added_rate': 0,
                    'quality_score': 0,
                    'improvement_ratio': 0
                }

            # 计算整体增值率
            exams = sorted(df['exam_id'].unique())
            if len(exams) < 2:
                return {
                    'value_added_rate': 0,
                    'quality_score': 0,
                    'improvement_ratio': 0
                }

            # 计算增值率
            first_exam = df[df['exam_id'] == exams[0]]['t_score'].mean()
            last_exam = df[df['exam_id'] == exams[-1]]['t_score'].mean()
            value_added_rate = float(last_exam - first_exam)

            # 计算质量评分
            quality_score = float((last_exam - 50) * 2 + 70)
            quality_score = min(max(quality_score, 0), 100)

            # 计算进步比例
            first_scores = df[df['exam_id'] == exams[0]].set_index('student_id')['t_score']
            last_scores = df[df['exam_id'] == exams[-1]].set_index('student_id')['t_score']
            improved = sum((last_scores - first_scores) > 0)
            total = len(first_scores)
            improvement_ratio = float(improved / total * 100) if total > 0 else 0

            return {
                'value_added_rate': value_added_rate,
                'quality_score': quality_score,
                'improvement_ratio': improvement_ratio
            }

        except Exception as e:
            logger.error(f"计算核心指标失败: {str(e)}")
            return {
                'value_added_rate': 0,
                'quality_score': 0,
                'improvement_ratio': 0
            }

    def _get_trend_data(self, df):
        """获取趋势数据"""
        try:
            if not isinstance(df, pd.DataFrame):
                return {'labels': [], 'values': []}

            # 按考试计算平均T分
            trend = df.groupby('exam_id')['t_score'].mean().reset_index()
            trend = trend.sort_values('exam_id')

            return {
                'labels': trend['exam_id'].tolist(),
                'values': [float(v) for v in trend['t_score'].tolist()]
            }

        except Exception as e:
            logger.error(f"获取趋势数据失败: {str(e)}")
            return {'labels': [], 'values': []}

    def _get_subject_analysis(self, df):
        """获取学科分析数据"""
        try:
            if not isinstance(df, pd.DataFrame):
                return {
                    'radar_data': {'indicators': [], 'values': []},
                    'pattern_distribution': {'labels': [], 'values': []},
                    'detailed_table': []
                }

            subjects = df['subject'].unique()
            subject_improvements = []

            for subject in subjects:
                subject_df = df[df['subject'] == subject]
                exams = sorted(subject_df['exam_id'].unique())
                if len(exams) >= 2:
                    first_mean = subject_df[subject_df['exam_id'] == exams[0]]['t_score'].mean()
                    last_mean = subject_df[subject_df['exam_id'] == exams[-1]]['t_score'].mean()
                    improvement = float(last_mean - first_mean)

                    # 计算进步率
                    first_scores = subject_df[subject_df['exam_id'] == exams[0]].set_index('student_id')['t_score']
                    last_scores = subject_df[subject_df['exam_id'] == exams[-1]].set_index('student_id')['t_score']
                    improved = sum((last_scores - first_scores) > 0)
                    total = len(first_scores)
                    progress_rate = float(improved / total * 100) if total > 0 else 0

                    subject_improvements.append({
                        'subject': subject,
                        'improvement': improvement,
                        'pattern': self._determine_pattern(improvement),
                        'progress_rate': progress_rate
                    })

            # 准备雷达图数据
            radar_data = {
                'indicators': [imp['subject'] for imp in subject_improvements],
                'values': [imp['improvement'] for imp in subject_improvements]
            }

            # 准备模式分布数据
            patterns = [imp['pattern'] for imp in subject_improvements]
            pattern_counts = {pattern: patterns.count(pattern) for pattern in set(patterns)}
            pattern_distribution = {
                'labels': list(pattern_counts.keys()),
                'values': list(pattern_counts.values())
            }

            return {
                'radar_data': radar_data,
                'pattern_distribution': pattern_distribution,
                'detailed_table': subject_improvements
            }

        except Exception as e:
            logger.error(f"获取学科分析数据失败: {str(e)}")
            return {
                'radar_data': {'indicators': [], 'values': []},
                'pattern_distribution': {'labels': [], 'values': []},
                'detailed_table': []
            }

    def _determine_pattern(self, improvement):
        """确定增长模式"""
        if improvement > 5:
            return '显著提升'
        elif improvement > 0:
            return '稳步提升'
        elif improvement > -5:
            return '略有下降'
        else:
            return '需要关注'

    def _calculate_subject_progress_rate(self, subject_df):
        """计算学科进步率"""
        try:
            exams = sorted(subject_df['exam_id'].unique())
            if len(exams) < 2:
                return 0

            first_scores = subject_df[subject_df['exam_id'] == exams[0]].set_index('student_id')['t_score']
            last_scores = subject_df[subject_df['exam_id'] == exams[-1]].set_index('student_id')['t_score']

            improved = sum((last_scores - first_scores) > 0)
            total = len(first_scores)

            return float(improved / total * 100) if total > 0 else 0

        except Exception as e:
            logger.error(f"计算学科进步率失败: {str(e)}")
            return 0

    def _get_schools_subject_analysis(self, df):
        """
        获取各学校学科增值对比分析，按学校人数降序排列。

        Args:
            df: T分数据DataFrame

        Returns:
            list: 包含各学校学科增值数据的列表，按学校人数降序排列
        """
        try:
            # 获取首次和最后一次考试
            exam_ids = sorted(df['exam_id'].unique())
            first_exam = exam_ids[0]
            last_exam = exam_ids[-1]

            # 获取所有学校列表及其学生人数
            # 使用最后一次考试的数据统计学校人数
            school_counts = df[
                (df['exam_id'] == last_exam)
            ]['student_id'].groupby(df['school_name']).nunique()

            # 按人数降序排列学校
            schools = school_counts.sort_values(ascending=False).index

            schools_data = []

            for school in schools:
                school_data = {
                    'school_name': school,
                    'student_count': int(school_counts[school])  # 添加学校总人数
                }

                # 获取该校的考试数据
                school_df = df[df['school_name'] == school]

                # 计算各学科的增值情况
                for subject in df['subject'].unique():
                    subject_df = school_df[school_df['subject'] == subject]

                    if not subject_df.empty:
                        # 获取首次和最后一次考试的T分均值
                        first_t_score = subject_df[subject_df['exam_id'] == first_exam]['t_score'].mean()
                        last_t_score = subject_df[subject_df['exam_id'] == last_exam]['t_score'].mean()

                        # 计算增值率
                        value_added = last_t_score - first_t_score if not pd.isna(first_t_score) and not pd.isna(
                            last_t_score) else 0

                        # 计算进步率
                        first_scores = subject_df[subject_df['exam_id'] == first_exam].set_index('student_id')[
                            't_score']
                        last_scores = subject_df[subject_df['exam_id'] == last_exam].set_index('student_id')['t_score']
                        improved = sum((last_scores - first_scores) > 0)
                        total = len(first_scores)
                        progress_rate = (improved / total * 100) if total > 0 else 0

                        # 存储学科数据
                        school_data[subject] = value_added
                        school_data[f'{subject}_details'] = {
                            'avg_score': float(last_t_score) if not pd.isna(last_t_score) else 0,
                            'progress_rate': float(progress_rate),
                            'student_count': int(total)
                        }
                    # 添加分层统计数据
               #         level_stats = self._calculate_level_statistics(subject_df, subject)
               #         school_data[f'{subject}_level_analysis'] = level_stats
                schools_data.append(school_data)

            return schools_data

        except Exception as e:
            logger.error(f"获取学校学科增值对比分析失败: {str(e)}")
            return []

    def _calculate_level_statistics(self, subject_df, subject):
        """
        计算学科分层统计数据

        Args:
            subject_df: 学科数据DataFrame
            subject: 学科代码

        Returns:
            dict: 包含各层次统计数据的字典
        """
        try:
            # 获取首次和最后一次考试
            exam_ids = sorted(subject_df['exam_id'].unique())
            first_exam = exam_ids[0]
            last_exam = exam_ids[-1]

            # 获取参加了两次考试的学生ID
            first_exam_students = set(subject_df[subject_df['exam_id'] == first_exam]['student_id'])
            last_exam_students = set(subject_df[subject_df['exam_id'] == last_exam]['student_id'])
            common_students = list(first_exam_students.intersection(last_exam_students))

            # 只选择参加了两次考试的学生数据
            valid_df = subject_df[subject_df['student_id'].isin(common_students)]

            # 获取最后一次考试的T分，用于分层
            last_scores = valid_df[valid_df['exam_id'] == last_exam]
            total_students = len(common_students)

            logger.info(f"首次考试学生数: {len(first_exam_students)}")
            logger.info(f"最后考试学生数: {len(last_exam_students)}")
            logger.info(f"共同参考学生数: {total_students}")

            # 定义分层
            levels = {
                'excellent': {'name': '卓越组', 'range': [80, 100], 'data': {}},  # 修改这里
                'good': {'name': '优秀组', 'range': [70, 80], 'data': {}},
                'medium': {'name': '良好组', 'range': [60, 70], 'data': {}},
                'pass': {'name': '合格组', 'range': [40, 60], 'data': {}},
                'improve': {'name': '提高组', 'range': [0, 40], 'data': {}}  # 修改这里
            }

            # 分层统计
            for level_key, level_info in levels.items():
                # 筛选该层次的学生
                if level_key == 'excellent':
                    level_students = last_scores[last_scores['t_score'] > level_info['range'][0]]
                elif level_key == 'improve':
                    level_students = last_scores[last_scores['t_score'] <= level_info['range'][1]]
                else:
                    level_students = last_scores[
                        (last_scores['t_score'] > level_info['range'][0]) &
                        (last_scores['t_score'] <= level_info['range'][1])
                        ]
                student_ids = level_students['student_id'].unique()
                student_count = len(student_ids)

                if student_count > 0:
                    # 获取该层次学生的首次和最后一次考试成绩
                    first_t_scores = valid_df[
                        (valid_df['exam_id'] == first_exam) &
                        (valid_df['student_id'].isin(student_ids))
                        ]['t_score']

                    last_t_scores = valid_df[
                        (valid_df['exam_id'] == last_exam) &
                        (valid_df['student_id'].isin(student_ids))
                        ]['t_score']

                    # 确保数据对齐
                    first_scores_dict = dict(zip(
                        valid_df[valid_df['exam_id'] == first_exam]['student_id'],
                        valid_df[valid_df['exam_id'] == first_exam]['t_score']
                    ))
                    last_scores_dict = dict(zip(
                        valid_df[valid_df['exam_id'] == last_exam]['student_id'],
                        valid_df[valid_df['exam_id'] == last_exam]['t_score']
                    ))

                    # 计算配对的分数差
                    paired_scores = [
                        (last_scores_dict[student_id] - first_scores_dict[student_id])
                        for student_id in student_ids
                        if student_id in first_scores_dict and student_id in last_scores_dict
                    ]

                    # 计算统计数据
                    first_mean = first_t_scores.mean()
                    last_mean = last_t_scores.mean()
                    value_added = last_mean - first_mean

                    # 计算进步率
                    improved = sum(diff > 0 for diff in paired_scores)
                    progress_rate = (improved / len(paired_scores) * 100) if paired_scores else 0

                    # 计算得分率
                    score_rate = (last_mean / 100 * 100)

                    levels[level_key]['data'] = {
                        'student_count': student_count,
                        'percentage': round(student_count / total_students * 100, 1),
                        'first_mean': round(first_mean, 1),
                        'last_mean': round(last_mean, 1),
                        'value_added': round(value_added, 1),
                        'progress_rate': round(progress_rate, 1),
                        'score_rate': round(score_rate, 1)
                    }

                    logger.debug(f"层次 {level_key} 统计数据: {levels[level_key]['data']}")

            return levels

        except Exception as e:
            logger.error(f"计算分层统计数据失败: {str(e)}")
            logger.exception(e)  # 输出完整的错误堆栈
            return {}