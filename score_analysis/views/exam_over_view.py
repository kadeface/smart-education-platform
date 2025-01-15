# score_analysis/views/exam_overview.py
import traceback

import numpy as np
from django.forms import IntegerField
from django.shortcuts import render
from django.views.generic import TemplateView
from django.db.models import Max, Min, Avg, Count, StdDev, Variance, F, Case, When
from scipy import stats
import json

from score_analysis.models import ScoreStudentBasic, BaseExamConfig
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
                template_name = 'score_analysis/overview/exam_overview_no_subject.html'

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
    def _get_basic_stats(self, exam_id):
        """获取基础成绩统计数据"""
        stats = ScoreStudentBasic.objects.filter(
            exam_id=exam_id,
            total_score__isnull=False
        )
        logger.info(f"基础成绩数据数量: {stats.count()}")
        return stats


    def _get_exam_stats(self, exam_id):
        """获取考试级别统计数据"""
        stats = ExamLevelStatistics.objects.filter(exam_id=exam_id)
        logger.info(f"考试统计数据数量: {stats.count()}")
        count = stats.count()
        if count == 0:
            logger.warning(f"未找到考试ID {exam_id} 的统计数据记录")
        return stats


    def _calculate_score_range(self, scores):
        """
        计算有效分数的极差（忽略0分）。

        Args:
            scores: 分数列表

        Returns:
            float: 分数极差
        """
        try:
            # 过滤掉0分
            valid_scores = [score for score in scores if score > 0]
            if not valid_scores:
                return 0
            return max(valid_scores) - min(valid_scores)
        except Exception as e:
            logger.error(f"计算分数极差时出错: {str(e)}")
            return 0

    def _get_exam_info(self, exam_id):
        """
           从base_exam_config获取考试基本信息。

           Args:
               exam_id: 考试ID

           Returns:
               dict: 包含考试基本信息的字典
           """
        try:
            exam = BaseExamConfig.objects.get(exam_id=exam_id)
            # 根据exam_id判断考试类型
            is_district_exam = 'DIST' in exam_id
            logger.info(f"考试ID: {exam_id}, 是否为区县考试: {is_district_exam}")
            return {
                'exam_name': exam.exam_name,
                'exam_date': exam.exam_date.strftime('%Y-%m-%d') if exam.exam_date else '',
                'exam_id': exam_id,
                'is_district_exam': is_district_exam
            }
        except BaseExamConfig.DoesNotExist:
            logger.error(f"未找到ID为{exam_id}的考试")
            return {}

        except Exception as e:
            logger.error(f"获取考试信息时出错: {str(e)}")
            return {}

    def get_context_data_with_subjects(self, exam_id):
        """
           获取分科考试的数据。

           Args:
               exam_id: 考试ID

           Returns:
               dict: 包含文理科统计数据的上下文
           """
        context = {}

        try:

            # 1. 获取所有基础数据
            basic_stats = self._get_basic_stats(exam_id)
            if not basic_stats.exists():
                raise ValueError(f"未找到ID为{exam_id}的考试基础数据")

            exam_stats = self._get_exam_stats(exam_id)
            exam_info = self._get_exam_info(exam_id)

            # 2. 设置基本考试信息
            context.update({
                'exam_info': exam_info,
                'exam_name': exam_info.get('exam_name', ''),
                'exam_date': exam_info.get('exam_date', ''),
            })
            logger.info(f"考试基本信息: {context['exam_info']}")

            # 3. 检查是否存在市级数据并设置考试类型
            has_city_data = exam_stats.filter(level_type='city').exists()
            context['exam_type'] = 'city' if has_city_data else 'district'
            logger.info(f"考试类型: {context['exam_type']}")

            if has_city_data:
                # 4. 处理市级考试数据
                city_context = self._process_city_stats(basic_stats, exam_stats)

                # 添加考试信息到科目数据中
                for subject in ['science', 'arts']:
                    if subject in city_context:
                        city_context[subject].update({
                            'exam_info': exam_info,
                            'is_district_exam': False
                        })

                context.update(city_context)

                # 5. 处理区县数据
                districts = exam_stats.filter(level_type='district').order_by('district_name', 'select_type')
                if districts.exists():
                    district_scores = self._get_district_scores(exam_id)
                    science_districts = []
                    arts_districts = []

                    for district in districts:
                        scores = district_scores.get(district.district_name, {}).get(district.select_type, [])
                        district_stats = self._prepare_district_stats(district, scores)
                        if district_stats:
                            if district.select_type == '理科':
                                science_districts.append(district_stats)
                            else:
                                arts_districts.append(district_stats)

                    # 将区县数据添加到相应科目中
                    if science_districts and 'science' in context:
                        context['science']['district_stats'] = science_districts
                        logger.info(f"理科区县数据数量: {len(science_districts)}")

                    if arts_districts and 'arts' in context:
                        context['arts']['district_stats'] = arts_districts
                        logger.info(f"文科区县数据数量: {len(arts_districts)}")

            else:
                # 6. 处理纯区县考试数据
                districts = exam_stats.filter(level_type='district').order_by('district_name', 'select_type')
                if districts.exists():
                    district_context = self._process_district_exam_stats(basic_stats, districts)

                    # 添加考试信息到科目数据中
                    for subject in ['science', 'arts']:
                        if subject in district_context:
                            district_context[subject].update({
                                'exam_info': exam_info,
                                'is_district_exam': True
                            })

                    context.update(district_context)
                    logger.info("已处理区县考试数据")
            # 在返回之前添加日志
          #  logger.info(f"science_data: {context.get('science')}")
          #  logger.info(f"arts_data: {context.get('arts')}")

            # 确保数据被正确序列化
            if 'science' in context:
                context['science_data'] = json.dumps(context['science'])
            if 'arts' in context:
                context['arts_data'] = json.dumps(context['arts'])
            return context

        except Exception as e:
            logger.error(f"获取分科考试数据时出错: {str(e)}")
            return {}





    def _get_rank_fields(self, rank_distribution):
        """
        从rank_distribution中动态获取排名字段。

        Args:
            rank_distribution: dict, 排名分布数据

        Returns:
            list: 排名字段列表，例如 ['top_10', 'top_20', ...]
        """
        try:
            # 获取第一个非空的rank_distribution
            sample_ranks = next(
                (ranks for ranks in rank_distribution.values() if ranks),
                {}
            )
            # 提取所有以'top_'开头的键，并排序
            rank_fields = sorted(
                [key for key in sample_ranks.keys() if key.startswith('top_')],
                key=lambda x: int(x.split('_')[1])  # 按数字大小排序
            )
            return rank_fields
        except Exception as e:
            logger.error(f"获取排名字段时出错: {str(e)}")
            return []

    def _process_city_stats(self, basic_stats, exam_stats):
        """处理市级统计数据"""
        context = {}
        city_stats = exam_stats.filter(level_type='city')

        # 处理理科数据
        science_data = self._get_subject_stats(
            basic_stats,
            city_stats,
            subject_type='理科'
        )
        if science_data:
            context['science'] = science_data
        #    logger.info(f"处理后的理科数据: {context['science']}")

        # 处理文科数据
        arts_data = self._get_subject_stats(
            basic_stats,
            city_stats,
            subject_type='文科'
        )
        if arts_data:
            context['arts'] = arts_data

        return context


    def _get_subject_stats(self, basic_stats, level_stats, subject_type, subject='total_score', district_name=None):
        """
           获取指定科目的统计数据。

           Args:
               basic_stats: 基础成绩查询集
               level_stats: 考试级别统计查询集
               subject_type: 科目类型（理科/文科）
               subject: 科目字段名称（默认为total_score，可以是chinese_score, math_score等）
               district_name: 区县名称（可选）

           Returns:
               dict: 包含统计数据的字典
           """
        try:
            # 构建基础查询条件
            filter_params = {'select_type': subject_type}
            # 只在非区县考试时添加district_name过滤
            # 直接判断是否存在市级数据
            is_city_exam = level_stats.filter(level_type='city').exists()

            # 如果是市级考试且提供了区县名称，则添加区县过滤
            if is_city_exam and district_name:
                filter_params['district_name'] = district_name

            # 记录查询条件
            logger.info(f"查询条件: {filter_params}")

            filtered_stats = basic_stats.filter(**filter_params)

            # 记录过滤后的数据量
            logger.info(f"过滤后的数据量: {filtered_stats.count()}")

            # 1. 获取基础统计数据
            basic_subject_stats = filtered_stats.aggregate(
                school_count=Count('school_name', distinct=True),
                student_count=Count('student_id'),
                max_score=Max(subject),
                min_score=Min(subject),
                avg_score=Avg(subject),
                std_dev=StdDev(subject)
            )

            # 2. 使用numpy和scipy进行统计分析
            scores = np.array([float(score) for score in filtered_stats.values_list(subject, flat=True)])
            if len(scores) > 0:
                # 2.1 计算分位数
                percentiles = [0.001, 1, 16, 55, 75, 80]
                score_percentiles = np.percentile(scores, percentiles)



                # 2.3 更新统计数据
                basic_subject_stats.update({
                    # 分位数统计
                    'q10_score': float(score_percentiles[0]),
                    'q20_score': float(score_percentiles[1]),
                    'q1_score': float(score_percentiles[2]),
                    'median_score': float(score_percentiles[3]),
                    'q3_score': float(score_percentiles[4]),
                    'q80_score': float(score_percentiles[5]),

                    # 集中趋势

                    'trimmed_mean': float(stats.trim_mean(scores, 0.1)),  # 去除极值的平均分

                    # 离散程度
                    'iqr': float(score_percentiles[4] - score_percentiles[2]),
                    'range': float(basic_subject_stats['max_score'] - basic_subject_stats['min_score']),
                    'cv': float(np.std(scores) / np.mean(scores)),

                    # 分布特征
                    'skewness': float(stats.skew(scores)),  # 使用 stats.skew
                    'kurtosis': float(stats.kurtosis(scores)),  # 使用 stats.kurtosis

                    # 正态性检验
                    'normality_stat': float(stats.normaltest(scores)[0]),  # 使用 stats.normaltest
                    'normality_pvalue': float(stats.normaltest(scores)[1])
                })

                # 2.4 计算Z分数（标准分）
                z_scores = stats.zscore(scores)  # 使用 stats.zscore
                basic_subject_stats.update({
                    'z_score_above_2': float(np.sum(z_scores > 2) / len(scores)),
                    'z_score_below_2': float(np.sum(z_scores < -2) / len(scores))
                })

            # 3. 获取最高分学校
            top_school = filtered_stats.filter(
                **{subject: basic_subject_stats['max_score']}
            ).values_list('school_name', flat=True).first() or "暂无数据"

            # 4. 获取统计数据和排名分布
            stats_obj = level_stats.filter(select_type=subject_type).first()
            rank_distribution = stats_obj.rank_distribution if stats_obj else {}
            rank_fields = self._get_rank_fields(rank_distribution)
            logger.info(f"获取到排名字段: {rank_fields}")

            # 在返回数据之前，添加学校统计数据
            if stats_obj:
                result = self._prepare_stats(stats_obj, basic_subject_stats, top_school)
                result['rank_fields'] = rank_fields

                # 获取学校统计数据
                schools_data = []
                school_names = filtered_stats.values_list('school_name', flat=True).distinct()

                for school_name in school_names:
                    # 获取该学校的分数
                    school_scores = filtered_stats.filter(
                        school_name=school_name
                    ).values_list(subject, flat=True)

                    scores_array = np.array([float(score) for score in school_scores if score > 0])

                    # 获取该学校的排名数据
                    school_ranks = rank_distribution.get(school_name, {})

                    if len(scores_array) > 0:
                        # 计算分位数
                        percentiles = np.percentile(scores_array, [5, 15, 55])

                        school_data = {
                            'school_name': school_name,
                            'student_count': len(scores_array),
                            'max_score': float(np.max(scores_array)),
                            'mean_score': float(np.mean(scores_array)),
                            'median_score': float(np.median(scores_array)),
                            'std_score': float(np.std(scores_array)),
                            'p5_score': float(percentiles[0]),
                            'p15_score': float(percentiles[1]),
                            'p55_score': float(percentiles[2]),
                            'skewness': float(stats.skew(scores_array)),
                            'kurtosis': float(stats.kurtosis(scores_array)),
                            # 添加排名数据
                            'top_10': school_ranks.get('top_10', 0),
                            'top_20': school_ranks.get('top_20', 0),
                            'top_50': school_ranks.get('top_50', 0),
                            'top_100': school_ranks.get('top_100', 0),
                            'top_200': school_ranks.get('top_200', 0),
                            'top_500': school_ranks.get('top_500', 0)
                        }
                        schools_data.append(school_data)
#                        logger.info(f"学校 {school_name} 的统计数据: {school_data}")

                # 添加学校统计数据到结果中
                result['school_stats'] = schools_data
                logger.info(f"{subject_type}学校统计数据数量: {len(schools_data)}")


                # 添加分数线的分布统计
                # 1. 获取分数线配置
                thresholds = self._get_threshold_scores(level_stats)

                # 2. 获取分数线分布统计（使用_get_threshold_distribution）
                if thresholds:
                    city_dist, district_dist, school_dist = self._get_threshold_distribution(
                        filtered_stats,
                        thresholds
                    )

                    # 将分数线分布添加到result中
                    result['threshold_distribution'] = {
                        'city': city_dist,
                        'districts': district_dist,
                        'schools': school_dist
                    }
                    result['thresholds'] = thresholds
                return result
            return None

        except Exception as e:
            logger.error(f"获取科目统计数据时出错: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            return None


    def _process_district_exam_stats(self, basic_stats, districts):
        """
           处理区县考试的统计数据。

           Args:
               basic_stats: QuerySet, 基础统计数据
               districts: QuerySet, 区县统计数据

           Returns:
               dict: 包含区县概况和学校详细数据的统计信息
           """
        try:
            context = {}
            district_stats_by_type = {stat.select_type: stat for stat in districts}

            # 处理理科数据
            if '理科' in district_stats_by_type:
                # 1. 获取理科概况数据
                science_data = self._get_subject_stats(
                    basic_stats=basic_stats,
                    level_stats=districts,
                    subject_type='理科',
                    district_name=None
                )

                if science_data:
                    # 2. 获取理科学校数据，传入 level_stats 参数
                    science_schools = self._get_schools_stats(
                        basic_stats=basic_stats,
                        level_stats=districts,  # 添加这个参数
                        subject_type='理科'
                    )
                    science_data['schools'] = science_schools
                    context['science'] = science_data

            # 处理文科数据
            if '文科' in district_stats_by_type:
                # 1. 获取文科概况数据
                arts_data = self._get_subject_stats(
                    basic_stats=basic_stats,
                    level_stats=districts,
                    subject_type='文科',
                    district_name=None
                )

                if arts_data:
                    # 2. 获取文科学校数据，传入 level_stats 参数
                    arts_schools = self._get_schools_stats(
                        basic_stats=basic_stats,
                        level_stats=districts,  # 添加这个参数
                        subject_type='文科'
                    )
                    arts_data['schools'] = arts_schools
                    context['arts'] = arts_data

            return context

        except Exception as e:
            logger.error(f"处理区县考试统计数据时出错: {str(e)}")
            return None


    def _get_schools_stats(self, basic_stats, level_stats, subject_type):
        """
           获取各学校的统计数据。

           Args:
               basic_stats: QuerySet, 已经过区县筛选的基础统计数据
               level_stats: QuerySet, 考试级别统计数据
               subject_type: str, 科目类型（理科/文科）

           Returns:
               list: 学校统计数据列表
           """
        try:
            # 获取排名分布数据
            stats = level_stats.filter(select_type=subject_type).first()
            rank_distribution = stats.rank_distribution if stats else {}

 #           logger.info(f"获取到排名分布数据: {rank_distribution}")

            # 按学校分组统计基础指标
            schools_stats = basic_stats.filter(
                select_type=subject_type
            ).values('school_name').annotate(
                student_count=Count('student_id'),
                max_score=Max('total_score'),
                mean_score=Avg('total_score'),
                std_score=StdDev('total_score')
            ).order_by('-mean_score')

            schools_data = []
            for school in schools_stats:
                school_name = school['school_name']

                # 获取该学校的排名数据
                school_ranks = rank_distribution.get(school_name, {})
               # logger.info(f"学校 {school_name} 的排名数据: {school_ranks}")
                # 获取该学校的分数
                scores = basic_stats.filter(
                    select_type=subject_type,
                    school_name=school_name
                ).values_list('total_score', flat=True)

                scores_array = np.array([float(score) for score in scores if score > 0])

                if len(scores_array) > 0:
                    school_data = {
                        'school_name': school_name,
                        'student_count': school['student_count'],
                        'max_score': float(school['max_score']),
                        'mean_score': float(school['mean_score']),
                        'median_score': float(np.median(scores_array)),
                        'std_score': float(school['std_score']),
                        #'skewness': float(stats.skew(scores_array)),
                        #'kurtosis': float(stats.kurtosis(scores_array))
                    }
                    # 动态添加排名分布数据
                    rank_fields = self._get_rank_fields(rank_distribution)
                    for field in rank_fields:
                        school_data[field] = int(school_ranks.get(field, 0))  # 确保转换为整数

                    schools_data.append(school_data)

            return schools_data

        except Exception as e:
            logger.error(f"获取学校统计数据时出错: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            return []


    def get_context_data_no_subjects(self, exam_id):
        """
           获取未分科考试的统计数据上下文

           Args:
               exam_id: 考试ID

           Returns:
               dict: 包含统计数据的上下文字典
           """
        try:
            # 获取基础数据
            basic_stats = self._get_basic_stats(exam_id)
            exam_stats = self._get_exam_stats(exam_id)
            exam_info = self._get_exam_info(exam_id)

            if not basic_stats.exists():
                logger.error(f"未找到考试ID {exam_id} 的基础统计数据")
                return {'error': '未找到统计数据'}

            # 准备上下文数据
            context = {
                'exam_info': exam_info
            }

            # 获取总分列表（排除0分）并转换为numpy数组
            total_scores = np.array([float(s.total_score) for s in basic_stats if s.total_score > 0])

            # 修改考试类型判断
            is_district_exam = 'DIST' in exam_id
            # 计算基础统计数据
            stats_data = {
                'is_district_exam': is_district_exam,
                'school_count': basic_stats.values('school_name').distinct().count(),
                'student_count': len(total_scores),
            }

            # 安全计算统计指标
            try:
                stats_data.update({
                    'mean_score': round(float(np.mean(total_scores)), 2) if len(total_scores) > 0 else 0,
                    'median_score': round(float(np.median(total_scores)), 2) if len(total_scores) > 0 else 0,
                    'std_score': round(float(np.std(total_scores)), 2) if len(total_scores) > 0 else 0,
                    'max_score': round(float(np.max(total_scores)), 2) if len(total_scores) > 0 else 0,
                    'range': round(float(self._calculate_score_range(total_scores)), 2),
                })

                # 单独处理偏度和峰度
                if len(total_scores) > 2:  # 需要至少3个数据点
                    stats_data.update({
                        'skewness': round(float(stats.skew(total_scores)), 4),
                        'kurtosis': round(float(stats.kurtosis(total_scores)), 4)
                    })
                else:
                    stats_data.update({
                        'skewness': 0,
                        'kurtosis': 0
                    })
            except Exception as e:
                logger.warning(f"计算统计指标时出错: {str(e)}")
                stats_data.update({
                    'mean_score': 0,
                    'median_score': 0,
                    'std_score': 0,
                    'max_score': 0,
                    'range': 0,
                    'skewness': 0,
                    'kurtosis': 0
                })

            # 获取最高分学校
            top_score_record = basic_stats.filter(total_score__gt=0).order_by('-total_score').first()
            stats_data['top_school'] = top_score_record.school_name if top_score_record else '暂无数据'

            if stats_data['is_district_exam']:
                # 区县考试：计算各学校统计
                school_stats = []
                for school in basic_stats.values('school_name').distinct():
                    school_name = school['school_name']
                    school_scores = np.array([float(s.total_score) for s in basic_stats.filter(
                        school_name=school_name,
                        total_score__gt=0
                    )])

                    if len(school_scores) > 0:
                        try:
                            school_stats.append({
                                'school_name': school_name,
                                'student_count': len(school_scores),
                                'max_score': round(float(np.max(school_scores)), 2),
                                'mean_score': round(float(np.mean(school_scores)), 2),
                                'median_score': round(float(np.median(school_scores)), 2),
                                'std_score': round(float(np.std(school_scores)), 2),
                                'skewness': round(float(stats.skew(school_scores)), 4) if len(school_scores) > 2 else 0,
                                'kurtosis': round(float(stats.kurtosis(school_scores)), 4) if len(school_scores) > 2 else 0
                            })
                        except Exception as e:
                            logger.warning(f"计算学校 {school_name} 统计指标时出错: {str(e)}")
                stats_data['school_stats'] = school_stats

            else:
                #市级考试：计算各区县统计
                district_stats = []
                for district in basic_stats.values('district_name').distinct():
                    district_name = district['district_name']
                    district_records = basic_stats.filter(
                        district_name=district_name,
                        total_score__gt=0
                    )
                    district_scores = np.array([float(r.total_score) for r in district_records])
                    if len(district_scores) > 0:
                        try:
                            # 获取该区县的统计信息
                            district_exam_stats = exam_stats.filter(district_name=district_name).first()
                            threshold_stats = district_exam_stats.threshold_stats if district_exam_stats else {}
                            top_score_record = district_records.order_by('-total_score').first()
                            district_stats.append({
                                'district_name': district_name,
                                'student_count': len(district_scores),
                                'max_score': round(float(np.max(district_scores)), 2),
                                'max_score_school': top_score_record.school_name,
                                'mean_score': round(float(np.mean(district_scores)), 2),
                                'median_score': round(float(np.median(district_scores)), 2),
                                'std_score': round(float(np.std(district_scores)), 2),
                                'skewness': round(float(stats.skew(district_scores)), 4) if len(district_scores) > 2 else 0,
                                'kurtosis': round(float(stats.kurtosis(district_scores)), 4) if len(
                                    district_scores) > 2 else 0,
                                'excellent_count': threshold_stats.get('excellent', {}).get('count', 0),
                                'pass_count': threshold_stats.get('pass', {}).get('count', 0),
                                'low_count': threshold_stats.get('low', {}).get('count', 0)
                            })
                        except Exception as e:
                            logger.warning(f"计算区县 {district_name} 统计指标时出错: {str(e)}")
                stats_data['district_stats'] = district_stats
                # 添加排名分布统计
                city_stats = exam_stats.filter(level_type='city').first()
                if city_stats and city_stats.rank_distribution:
                    # 获取所有排名类型（如 top_10, top_50 等）
                    rank_types = set()
                    for district_data in city_stats.rank_distribution.values():
                        rank_types.update(district_data.keys())
                    rank_types = sorted(rank_types, key=lambda x: int(x.split('_')[1]))  # 按数字大小排序
                    # 准备排名分布数据
                    rank_distribution = []
                    for district_name, district_data in city_stats.rank_distribution.items():
                        district_ranks = {
                            'district_name': district_name,
                        }
                        # 添加每个排名段的数据
                        for rank_type in rank_types:
                            district_ranks[rank_type] = district_data.get(rank_type, 0)
                        rank_distribution.append(district_ranks)
                    stats_data['rank_types'] = rank_types  # 用于模板动态生成表头
                    stats_data['rank_distribution'] = rank_distribution
                    logger.info(f"排名分布数据: {rank_distribution}")
                else:
                    logger.warning(f"未找到考试ID {exam_id} 的市级排名分布数据")
                context['overall_data'] = stats_data
                return context
        except Exception as e:
            logger.error(f"处理未分科考试数据时出错: {str(e)}")
            return {'error': str(e)}

    def _prepare_stats(self, stats, basic_stats, top_school):
        """
           准备统计数据。

           Args:
               stats: 统计对象
               basic_stats: 基础统计数据
               top_school: 最高分学校

           Returns:
               dict: 处理后的统计数据
           """
        if not stats:
            return None

        threshold_stats = self.parse_json(stats.threshold_stats) if stats.threshold_stats else {}
        school_distribution = self.parse_json(stats.school_distribution) if stats.school_distribution else {}
        rank_distribution = self.parse_json(stats.rank_distribution) if stats.rank_distribution else {}

        # 2. 获取分数线数据（用于分布统计）
        thresholds = {}
        if threshold_stats:
            for name, data in threshold_stats.items():
                if "score" in data:
                    thresholds[name] = {
                        "score": float(data["score"]),
                        "count": data.get("count", 0),
                        "rate": data.get("rate", 0)
                    }
        return {
            # 基础计数
            'school_count': basic_stats.get('school_count', 0),
            'student_count': stats.student_count,

            # 集中趋势
            'max_score': round(float(basic_stats.get('max_score', 0)), 2),
            'min_score': round(float(basic_stats.get('min_score', 0)), 2),
            'mean_score': round(float(basic_stats.get('avg_score', 0)), 2),
            'median_score': round(float(basic_stats.get('median_score', 0)), 2),
            'trimmed_mean': round(float(basic_stats.get('trimmed_mean', 0)), 2),

            # 离散程度
            'std_score': round(float(basic_stats.get('std_dev', 0)), 2),
            'iqr': round(float(basic_stats.get('iqr', 0)), 2),
            'range': round(float(basic_stats.get('range', 0)), 2),
            'cv': round(float(basic_stats.get('cv', 0)), 4),

            # 分位数
            'q10_score': round(float(basic_stats.get('q10_score', 0)), 2),
            'q20_score': round(float(basic_stats.get('q20_score', 0)), 2),
            'q1_score': round(float(basic_stats.get('q1_score', 0)), 2),
            'q3_score': round(float(basic_stats.get('q3_score', 0)), 2),
            'q80_score': round(float(basic_stats.get('q80_score', 0)), 2),

            # 分布特征
            'skewness': round(float(basic_stats.get('skewness', 0)), 4),
            'kurtosis': round(float(basic_stats.get('kurtosis', 0)), 4),
            'normality_stat': round(float(basic_stats.get('normality_stat', 0)), 4),
            'normality_pvalue': round(float(basic_stats.get('normality_pvalue', 0)), 4),

            # Z分数统计
            'z_score_above_2': round(float(basic_stats.get('z_score_above_2', 0)), 4),
            'z_score_below_2': round(float(basic_stats.get('z_score_below_2', 0)), 4),

            # 其他信息
            'top_school': top_school,
            'threshold_stats': threshold_stats,
            'school_stats': school_distribution,
            'rank_distribution': rank_distribution
        }


    def _prepare_district_stats(self, district, scores=None):
        """
           准备区县统计数据，使用实时计算。

           Args:
               district: 区县统计对象
               scores: 列表，包含元组 (score, school_name)

           Returns:
               dict: 处理后的区县统计数据
           """
#        logger.info(f"准备区县 {district.district_name} 的统计数据")
#        logger.info(f"收到的分数数据数量: {len(scores) if scores else 0}")

        if not district or not scores:
            logger.warning(f"缺少必要数据: district={bool(district)}, scores={bool(scores)}")
            return None

        try:
            # 分离分数和学校名
            scores_data = np.array([(float(score), school) for score, school in scores if float(score) > 0])
            if len(scores_data) == 0:
#                logger.warning(f"区县 {district.district_name} 没有有效分数数据")
                return None

            valid_scores = scores_data[:, 0].astype(float)  # 分数列表
            schools = scores_data[:, 1]  # 学校名列表

            # 计算基本统计量
            mean_score = np.mean(valid_scores)
            median_score = np.median(valid_scores)
            std_score = np.std(valid_scores)

            # 最高分及其学校
            max_score_idx = np.argmax(valid_scores)
            max_score = valid_scores[max_score_idx]
            max_score_school = schools[max_score_idx]

            # 最低分
            min_score = np.min(valid_scores)

            # 计算分位数
            p5_score = np.percentile(valid_scores, 95)  # 前5%（从高到低）
            p15_score = np.percentile(valid_scores, 85)  # 前15%
            p55_score = np.percentile(valid_scores, 45)  # 前55%

            # 计算分布特征
            skewness = stats.skew(valid_scores)
            kurtosis = stats.kurtosis(valid_scores)

            result = {
                'district_name': district.district_name,
                'select_type': district.select_type,
                'student_count': len(valid_scores),
                'mean_score': round(float(mean_score), 2),
                'median_score': round(float(median_score), 2),
                'std_score': round(float(std_score), 2),
                'max_score': round(float(max_score), 2),
                'max_score_school': max_score_school,
                'min_score': round(float(min_score), 2),
                'range': round(float(max_score - min_score), 2),
                'p5_score': round(float(p5_score), 2),  # 前5%
                'p15_score': round(float(p15_score), 2),  # 前15%
                'p55_score': round(float(p55_score), 2),  # 前55%
                'skewness': round(float(skewness), 4),
                'kurtosis': round(float(kurtosis), 4)
            }

#            logger.info(f"成功生成区县统计数据: {result}")
            return result

        except Exception as e:
            logger.error(f"处理区县 {district.district_name} 统计数据时出错: {str(e)}")
            return None

    def _get_district_scores(self,exam_id):
        """
           获取各区县的分数和学校数据。

           Returns:
               dict: {
                   '区县1': {
                       '理科': [(分数, 学校名), ...],
                       '文科': [(分数, 学校名), ...]
                   }
               }
           """
        scores = ScoreStudentBasic.objects.filter(
            exam_id=exam_id
        ).values('district_name', 'select_type', 'total_score', 'school_name')

        district_scores = {}
        for score in scores:
            district = score['district_name']
            subject_type = score['select_type']
            total_score = score['total_score']
            school_name = score['school_name']

            if district not in district_scores:
                district_scores[district] = {'理科': [], '文科': []}
            if subject_type in ['理科', '文科']:
                district_scores[district][subject_type].append((total_score, school_name))

        return district_scores


    def parse_json(self,data):
        if isinstance(data, dict):
            return data
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return {}
        return {}


    def _calculate_threshold_stats(self, scores, thresholds):
        """
           一次性计算所有分数线的分布统计。

           Args:
               scores: numpy.array, 所有分数数组
               thresholds: dict, 分数线信息

           Returns:
               dict: 分数线分布统计
               {
                   "total": 15000,
                   "thresholds": {
                       "≥680分(C9)": {"count": 1500, "rate": 0.1},
                       ...
                   }
               }
           """
        try:
            # 转换为numpy数组（如果不是）
            scores_array = np.array(scores)
            total = len(scores_array)

            if total == 0:
                return {"total": 0, "thresholds": {}}

            # 创建一次性的布尔掩码数组
            threshold_stats = {}
            for name, data in thresholds.items():
                score = data["score"]
                # 一次性计算所有大于等于该分数线的数量
                count = np.sum(scores_array >= score)
                rate = (count / total * 100) if total > 0 else 0

                threshold_stats[f"≥{score}分({name})"] = {
                    "count": int(count),
                    "rate": round(rate, 2)
                }

            return {
                "total": total,
                "thresholds": threshold_stats
            }
        except Exception as e:
            logger.error(f"计算分数线分布统计时出错: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            return {
                "total": 0,
                "thresholds": {},
                "error": str(e)
            }


    def _get_threshold_distribution(self, filtered_stats, thresholds):
        """
           从已过滤的查询集获取各层级的分数线分布。

           Args:
               filtered_stats: QuerySet, 已经过滤好的成绩查询集
               thresholds: dict, 分数线信息

           Returns:
               tuple: (city_stats, district_stats, school_stats)
           """
        try:
            # 使用Django ORM的聚合和分组功能

            # 构建动态的条件表达式
            conditions = []
            for name, data in thresholds.items():
                score = data["score"]
                conditions.append(
                    Count(Case(
                        When(total_score__gte=score, then=1),
                        output_field=IntegerField(),
                    )))

            # 学校级统计
            school_stats = filtered_stats.values(
                'school_name', 'district_name'
            ).annotate(
                total=Count('id'),
                **{f"ge_{score}": cond for score, cond in zip(thresholds.keys(), conditions)}
            )
            # 记录学校统计结果
            logger.info(f"学校级统计结果: {list(school_stats)}")
            # 区县级统计
            district_stats = filtered_stats.values(
                'district_name'
            ).annotate(
                total=Count('id'),
                **{f"ge_{score}": cond for score, cond in zip(thresholds.keys(), conditions)}
            )

            # 市级统计
            city_stats = filtered_stats.aggregate(
                total=Count('id'),
                **{f"ge_{score}": cond for score, cond in zip(thresholds.keys(), conditions)}
            )

            return self._format_threshold_stats(city_stats, district_stats, school_stats, thresholds)

        except Exception as e:
            logger.error(f"获取分数线分布统计时出错: {str(e)}")
            return {}, {}, {}


    def _format_threshold_stats(self, city_stats, district_stats, school_stats, thresholds):
        try:
            # 添加日志查看输入数据
            logger.info(f"格式化前的数据:")
            logger.info(f"city_stats: {city_stats}")
            logger.info(f"thresholds: {thresholds}")

            # 1. 格式化市级数据
            city_distribution = {
                "total": city_stats.get('total', 0),
                "thresholds": {}
            }

            # 处理市级各分数线统计
            for name, data in thresholds.items():
                score = data["score"]
                # 修改这里的键名匹配
                count = city_stats.get(f"ge_{name}", 0)  # 使用name而不是score
                rate = round((count / city_distribution["total"] * 100), 2) if city_distribution["total"] > 0 else 0
                city_distribution["thresholds"][f"≥{score}分({name})"] = {
                    "count": count,
                    "rate": rate
                }

            # 2. 格式化区县数据
            district_distribution = {}
            for dist in district_stats:
                district_name = dist['district_name']
                total = dist['total']
                thresholds_data = {}

                for name, data in thresholds.items():
                    score = data["score"]
                    # 这里也需要修改键名匹配
                    count = dist.get(f"ge_{name}", 0)  # 使用name而不是score
                    rate = round((count / total * 100), 2) if total > 0 else 0
                    thresholds_data[f"≥{score}分({name})"] = {
                        "count": count,
                        "rate": rate
                    }

                district_distribution[district_name] = {
                    "total": total,
                    "thresholds": thresholds_data
                }

            # 3. 格式化学校数据
            school_distribution = {}
            for school in school_stats:
                district_name = school['district_name']
                school_name = school['school_name']
                total = school['total']

                if district_name not in school_distribution:
                    school_distribution[district_name] = {}

                thresholds_data = {}
                for name, data in thresholds.items():
                    score = data["score"]
                    # 这里也需要修改键名匹配
                    count = school.get(f"ge_{name}", 0)  # 使用name而不是score
                    rate = round((count / total * 100), 2) if total > 0 else 0
                    thresholds_data[f"≥{score}分({name})"] = {
                        "count": count,
                        "rate": rate
                    }

                school_distribution[district_name][school_name] = {
                    "total": total,
                    "thresholds": thresholds_data
                }

            return city_distribution, district_distribution, school_distribution

        except Exception as e:
            logger.error(f"格式化分数线分布统计数据时出错: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            return {}, {}, {}


    def _get_threshold_scores(self, exam_stats):
        """
           从考试统计数据中获取分数线信息。

           Args:
               exam_stats: ExamLevelStatistics对象

           Returns:
               dict: 排序后的分数线字典
           """
        try:
            # 先检查是否是区县考试
            is_district_exam = not exam_stats.filter(level_type='city').exists()

            if is_district_exam:
                # 区县考试：获取区县级数据
                stats = exam_stats.first()
                logger.info("获取区县考试分数线数据")
            else:
                # 市级考试：获取市级数据
                stats = exam_stats.filter(level_type='city').first()
                logger.info("获取市级考试分数线数据")

            if not stats or not stats.threshold_stats:
                logger.warning(f"未找到{'区县' if is_district_exam else '市级'}分数线数据")
                return {}

            # 解析threshold_stats
            threshold_data = self.parse_json(stats.threshold_stats)
            logger.info(f"解析到的分数线数据: {threshold_data}")

            # 构建并排序分数线数据
            thresholds = {}
            level_mapping = {
                "C9": 6, "985": 5, "211": 4,
                "特控": 3, "本科": 2, "专科": 1
            }

            for name, data in threshold_data.items():
                if "score" in data:
                    thresholds[name] = {
                        "score": float(data["score"]),
                        "level": level_mapping.get(name, 0)
                    }

            # 按分数线从高到低排序
            sorted_thresholds = dict(sorted(
                thresholds.items(),
                key=lambda x: (x[1]["score"], x[1]["level"]),
                reverse=True
            ))

            logger.info(f"返回的排序后分数线数据: {sorted_thresholds}")
            return sorted_thresholds

        except Exception as e:
            logger.error(f"获取分数线数据时出错: {str(e)}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            return {}