from collections import Counter

import numpy as np
import pandas as pd
from django.db.models import Max, Min, Avg, Count

from score_analysis.models import BaseExamConfig, ScoreStudentBasic, BaseSubjectConfig
from score_analysis.models.Tracking import TrackingRecord
from score_analysis.models.statistics import StatisticsExamIndicators, ExamScoreLines, ExamLevelStatistics, \
    ExamLevelAnalysisConfig
from collections import defaultdict
import logging
logger = logging.getLogger(__name__)

class StatisticsGenerator:
    """统计数据生成器"""
    def _is_division_exam(self, exam_config):
        """判断是否为分科考试"""
        """判断是否为分科考试"""
        # 添加日志记录
        # 检查是否包含 -H- 并且后面是年份
        is_high_school = '-H-' in exam_config.exam_id and exam_config.exam_id.split('-H-')[1].isdigit()
        is_not_first_semester = exam_config.semester not in ['H1-1']

        is_division = is_high_school and is_not_first_semester

        logger.info(f"是否分科考试: {is_division}")
        return is_division

    def _get_districts(self, exam_id):
        """获取考试涉及的区县列表"""
        from score_analysis.models import ScoreStudentBasic
        return ScoreStudentBasic.objects.filter(
            exam_id=exam_id
        ).values_list('district_name', flat=True).distinct()

    def _get_exam_type(self, exam_id):
        """判断考试类型（市级/区县）"""
        if 'CITY' in exam_id:
            return 'city'
        elif 'DIST' in exam_id:
            return 'district'
        else:
            logger.warning(f"无法判断考试类型: {exam_id}")
            return None

    def generate_exam_statistics(self, exam_id):
        """生成考试统计数据
        Args:
            exam_id: 考试ID
        """
        try:
            # 先删除此次考试的所有统计数据
            ExamLevelStatistics.objects.filter(exam_id=exam_id).delete()
            logger.info(f"已清理考试 {exam_id} 的历史统计数据")

            exam_config = BaseExamConfig.objects.get(exam_id=exam_id)
            is_division = self._is_division_exam(exam_config)
            exam_type = self._get_exam_type(exam_id)

            logger.info(f"开始生成统计数据: exam_id={exam_id}, exam_type={exam_type}, is_division={is_division}")

            if exam_type == 'city':
                # 只生成市级统计
                self._generate_city_statistics(exam_id, is_division)
                # 对于市级考试，还需要生成每个区县的统计
                districts = self._get_districts(exam_id)
                for district in districts:
                    self._generate_district_statistics(exam_id, district, is_division)
            elif exam_type == 'district':
                # 生成区县级统计
                districts = self._get_districts(exam_id)
                for district in districts:
                    self._generate_district_statistics(exam_id, district, is_division)
            else:
                raise ValueError(f"不支持的考试类型: {exam_id}")

            logger.info(f"考试统计数据生成完成: exam_id={exam_id}")

        except Exception as e:
            logger.error(f"生成考试统计数据失败: exam_id={exam_id}, error={str(e)}")
            raise

    def _generate_district_statistics(self, exam_id, district, is_division):
        """生成区县级统计数据"""
        try:
            # 获取实际的 select_type 值
            actual_select_types = list(ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                district_name=district
            ).values_list('select_type', flat=True).distinct())

            logger.info(f"区县 {district} 的 select_type 值: {actual_select_types}")

            # 根据是否分科设置预期的 select_type 值
            expected_select_types = ['理科', '文科'] if is_division else ['未确定']

            # 使用数据库中实际存在的 select_type 值
            select_types = [st for st in expected_select_types if st in actual_select_types]

            if not select_types:
                logger.warning(f"未找到预期的科目类型，使用数据库中的实际值: {actual_select_types}")
                select_types = actual_select_types

            for select_type in select_types:
                records = ScoreStudentBasic.objects.filter(
                    exam_id=exam_id,
                    select_type=select_type,
                    district_name=district
                )

                if not records.exists():
                    continue

                # 获取所有需要的数据
                scores_with_details = list(records.values(
                    'total_score',
                    'school_name',
                    'math',
                    'chinese',
                    'exam_id',
                    'select_type'
                ).order_by('-total_score'))

                # 使用 NumPy 计算排名分布
                school_rank_counts = self._calculate_rank_distribution(scores_with_details)

                # 使用 NumPy 计算基础统计数据
                scores_array = np.array([float(r['total_score']) for r in scores_with_details])
                total_students = len(scores_array)

                if total_students > 0:
                    stats_data = {
                        'student_count': total_students,
                        'max_score': float(np.max(scores_array)),
                        'min_score': float(np.min(scores_array)),
                        'mean_score': float(np.mean(scores_array)),
                        'median_score': float(np.median(scores_array)),
                        'std_dev': float(np.std(scores_array)) if total_students > 1 else 0
                    }
                    # 计算分位数
                    q80_score = float(np.percentile(scores_array, 80))
                    q20_score = float(np.percentile(scores_array, 20))
                    q10_score = float(np.percentile(scores_array, 10))
                    # 根据是否分科决定使用哪种阈值统计
                    if is_division:
                        # 使用配置的分数线
                        threshold_stats = self._calculate_threshold_stats(records)
                        if not threshold_stats:
                            logger.warning(
                                f"未找到分数线配置，使用分位数: exam_id={exam_id}, district={district}, select_type={select_type}")
                            threshold_stats = {
                                'excellent': {'score': q80_score},
                                'pass': {'score': q20_score},
                                'low': {'score': q10_score}
                            }
                    else:
                        # 未分科使用分位数
                        # 计算达线人数和比例
                        excellent_count = len([s for s in scores_array if s >= q80_score])
                        pass_count = len([s for s in scores_array if s >= q20_score])
                        low_count = len([s for s in scores_array if s <= q10_score])

                        threshold_stats = {
                            'excellent': {
                                'score': q80_score,
                                'count': excellent_count,
                                'rate': round(excellent_count * 100 / total_students, 2)
                            },
                            'pass': {
                                'score': q20_score,
                                'count': pass_count,
                                'rate': round(pass_count * 100 / total_students, 2)
                            },
                            'low': {
                                'score': q10_score,
                                'count': low_count,
                                'rate': round(low_count * 100 / total_students, 2)
                            }
                        }
                    # 计算分位数
                    q80_score = float(np.percentile(scores_array, 80))
                    q20_score = float(np.percentile(scores_array, 20))
                    q10_score = float(np.percentile(scores_array, 10))

                    # 生成学校分布
                    from collections import defaultdict

                    # 收集每个学校的成绩
                    school_scores = defaultdict(list)
                    for record in scores_with_details:
                        school_scores[record['school_name']].append(float(record['total_score']))

                    # 计算每个学校的统计数据
                    school_distribution = {}
                    for school_name, scores in school_scores.items():
                        scores_array = np.array(scores)
                        school_distribution[school_name] = {
                            'student_count': len(scores),
                            'avg_score': float(np.mean(scores_array)),
                            'max_score': float(np.max(scores_array)),
                            'min_score': float(np.min(scores_array))
                        }

                    # 保存区县统计数据
                    ExamLevelStatistics.objects.update_or_create(
                        exam_id=exam_id,
                        select_type=select_type,
                        level_type='district',
                        district_name=district,
                        defaults={
                            'student_count': stats_data['student_count'],
                            'max_score': stats_data['max_score'],
                            'min_score': stats_data['min_score'],
                            'mean_score': stats_data['mean_score'],
                            'median_score': stats_data['median_score'],
                            'std_dev': stats_data['std_dev'],
                            'q80_score': q80_score,
                            'q20_score': q20_score,
                            'q10_score': q10_score,
                            'excellent_rate': 20.0,
                            'pass_rate': 80.0,
                            'low_score_rate': 10.0,
                            'rank_distribution': school_rank_counts,
                            'school_distribution': school_distribution,
                            'threshold_stats': threshold_stats
                            }

                    )

                    logger.info(
                        f"区县统计数据已生成: exam_id={exam_id}, district={district}, select_type={select_type}")

        except Exception as e:
            logger.error(f"生成区县统计数据失败: exam_id={exam_id}, district={district}, error={str(e)}")
            logger.exception(e)
            raise

    def _generate_city_statistics(self, exam_id, is_division):
        """生成市级统计数据"""
        try:
            # 获取实际的 select_type 值
            actual_select_types = list(ScoreStudentBasic.objects.filter(
                exam_id=exam_id
            ).values_list('select_type', flat=True).distinct())

            logger.info(f"数据库中的 select_type 值: {actual_select_types}")

            # 根据是否分科设置预期的 select_type 值
            expected_select_types = ['理科', '文科'] if is_division else ['未确定']

            # 使用数据库中实际存在的 select_type 值
            select_types = [st for st in expected_select_types if st in actual_select_types]

            if not select_types:
                logger.warning(f"未找到预期的科目类型，使用数据库中的实际值: {actual_select_types}")
                select_types = actual_select_types

            for select_type in select_types:
                records = ScoreStudentBasic.objects.filter(
                    exam_id=exam_id,
                    select_type=select_type
                )

                if not records.exists():
                    logger.warning(f"未找到统计数据: exam_id={exam_id}, select_type={select_type}")
                    continue

                # 获取所有需要的数据
                scores_with_details = list(records.values(
                    'total_score',
                    'district_name',
                    'math',
                    'chinese',
                    'exam_id',
                    'select_type'
                ))

                # 使用已有方法计算排名分布
                district_rank_counts = self._calculate_rank_distribution(scores_with_details, 'district_name')

                # 使用 NumPy 计算基础统计数据
                scores_array = np.array([float(r['total_score']) for r in scores_with_details])
                total_students = len(scores_array)

                if total_students > 0:
                    stats_data = {
                        'student_count': total_students,
                        'max_score': float(np.max(scores_array)),
                        'min_score': float(np.min(scores_array)),
                        'mean_score': float(np.mean(scores_array)),
                        'median_score': float(np.median(scores_array)),
                        'std_dev': float(np.std(scores_array)) if total_students > 1 else 0
                    }

                    # 计算分位数
                    q80_score = float(np.percentile(scores_array, 80))
                    q20_score = float(np.percentile(scores_array, 20))
                    q10_score = float(np.percentile(scores_array, 10))
                    # 根据是否分科决定使用哪种阈值统计
                    if is_division:
                        # 使用配置的分数线
                        threshold_stats = self._calculate_threshold_stats(records)
                        if not threshold_stats:
                            logger.warning(f"未找到分数线配置，使用分位数: exam_id={exam_id}, select_type={select_type}")
                            threshold_stats = {
                                'excellent': {'score': q80_score},
                                'pass': {'score': q20_score},
                                'low': {'score': q10_score}
                            }
                    else:
                        # 未分科使用分位数
                        threshold_stats = {
                            'excellent': {'score': q80_score},
                            'pass': {'score': q20_score},
                            'low': {'score': q10_score}
                        }
                    # 生成区县分布
                    from collections import defaultdict

                    # 收集每个区县的成绩
                    district_scores = defaultdict(list)
                    for record in scores_with_details:
                        district_scores[record['district_name']].append(float(record['total_score']))

                    # 计算每个区县的统计数据
                    district_distribution = {}
                    for district_name, scores in district_scores.items():
                        scores_array = np.array(scores)
                        district_distribution[district_name] = {
                            'student_count': len(scores),
                            'avg_score': float(np.mean(scores_array)),
                            'max_score': float(np.max(scores_array)),
                            'min_score': float(np.min(scores_array))
                        }

                    # 保存市级统计数据
                    ExamLevelStatistics.objects.update_or_create(
                        exam_id=exam_id,
                        select_type=select_type,
                        level_type='city',
                        defaults={
                            'student_count': stats_data['student_count'],
                            'max_score': stats_data['max_score'],
                            'min_score': stats_data['min_score'],
                            'mean_score': stats_data['mean_score'],
                            'median_score': stats_data['median_score'],
                            'std_dev': stats_data['std_dev'],
                            'q80_score': q80_score,
                            'q20_score': q20_score,
                            'q10_score': q10_score,
                            'excellent_rate': 20.0,
                            'pass_rate': 80.0,
                            'low_score_rate': 10.0,
                            'rank_distribution': district_rank_counts,
                            'school_distribution': district_distribution,
                            'threshold_stats': threshold_stats

                        }
                    )

                    logger.info(f"市级统计数据已生成: exam_id={exam_id}, select_type={select_type}")

        except Exception as e:
            logger.error(f"生成市级统计数据失败: exam_id={exam_id}, error={str(e)}")
            logger.exception(e)
            raise
    def _generate_total_statistics(self, exam_id, scores, level_type, district_name=None, select_type=None):
        """生成总分统计数据"""
        # 计算基础统计指标
        stats = {
            'exam_id': exam_id,
            'level_type': level_type,
            'select_type': select_type or '未分科',
            'student_count': scores.count(),
            'max_score': scores.aggregate(Max('total_score'))['total_score__max'],
            'min_score': scores.aggregate(Min('total_score'))['total_score__min'],
            'mean_score': scores.aggregate(Avg('total_score'))['total_score__avg'],
        }

        if district_name:
            stats['district_name'] = district_name

        # 计算四分位数
        scores_list = list(scores.values_list('total_score', flat=True))
        stats.update(self._calculate_quantiles(scores_list))

        # 计算及格率等
        stats.update(self._calculate_rates(scores_list))

        # 计算学校分布
        stats['school_distribution'] = self._calculate_school_distribution(scores)

        # 计算排名分布
        stats['rank_distribution'] = self._calculate_rank_distribution(scores)

        # 计算分数线达线情况
        stats['threshold_stats'] = self._calculate_threshold_stats(scores)

        # 保存或更新统计数据
        StatisticsExamIndicators.objects.update_or_create(
            exam_id=exam_id,
            level_type=level_type,
            district_name=district_name,
            select_type=select_type or '未分科',
            subject__isnull=True,
            defaults=stats
        )

    def _generate_subject_statistics(self, exam_id, scores, level_type, district_name=None, select_type=None):
        """生成学科统计数据"""
        # 获取考试科目
        subjects = BaseSubjectConfig.objects.filter(exam_id=exam_id)

        for subject in subjects:
            # 获取科目成绩
            subject_scores = [
                score.subject_scores.get(subject.code, 0)
                for score in scores
            ]

            if not subject_scores:
                continue

            # 计算科目统计数据
            stats = {
                'exam_id': exam_id,
                'subject': subject,
                'level_type': level_type,
                'select_type': select_type or '未分科',
                'student_count': len(subject_scores),
                'max_score': max(subject_scores),
                'min_score': min(subject_scores),
                'mean_score': sum(subject_scores) / len(subject_scores)
            }

            if district_name:
                stats['district_name'] = district_name

            # 计算四分位数
            stats.update(self._calculate_quantiles(subject_scores))

            # 计算及格率等
            stats.update(self._calculate_rates(subject_scores))

            # 保存或更新统计数据
            StatisticsExamIndicators.objects.update_or_create(
                exam_id=exam_id,
                subject=subject,
                level_type=level_type,
                district_name=district_name,
                select_type=select_type or '未分科',
                defaults=stats
            )

    def _calculate_quantiles(self, scores):
        """计算四分位数
        Args:
            scores: 分数列表
        Returns:
            dict: 四分位数统计
        """
        try:
            if not scores:
                return {
                    'q80_score': 0,
                    'median_score': 0,
                    'q20_score': 0,
                    'q10_score': 0
                }

            scores = sorted([s for s in scores if s > 0])  # 排除无效成绩
            if not scores:
                return {
                    'q80_score': 0,
                    'median_score': 0,
                    'q20_score': 0,
                    'q10_score': 0
                }

            n = len(scores)
            return {
                'q80_score': scores[int(n * 0.8)] if n > 0 else 0,
                'median_score': scores[int(n * 0.5)] if n > 0 else 0,
                'q20_score': scores[int(n * 0.2)] if n > 0 else 0,
                'q10_score': scores[int(n * 0.1)] if n > 0 else 0
            }
        except Exception as e:
            logger.error(f"计算四分位数失败: error={str(e)}")
            return {
                'q80_score': 0,
                'median_score': 0,
                'q20_score': 0,
                'q10_score': 0
            }

    def _calculate_rates(self, scores, excellent_threshold=0.85, pass_threshold=0.60, low_threshold=0.30):
        """计算及格率等
        Args:
            scores: 分数列表
            excellent_threshold: 优秀线比例
            pass_threshold: 及格线比例
            low_threshold: 低分线比例
        Returns:
            dict: 比率统计
        """
        try:
            if not scores:
                return {
                    'excellent_rate': 0,
                    'pass_rate': 0,
                    'low_score_rate': 0
                }

            valid_scores = [s for s in scores if s > 0]
            if not valid_scores:
                return {
                    'excellent_rate': 0,
                    'pass_rate': 0,
                    'low_score_rate': 0
                }

            max_score = max(valid_scores)
            excellent_line = max_score * excellent_threshold
            pass_line = max_score * pass_threshold
            low_line = max_score * low_threshold

            total = len(valid_scores)
            return {
                'excellent_rate': round(sum(1 for s in valid_scores if s >= excellent_line) * 100 / total, 2),
                'pass_rate': round(sum(1 for s in valid_scores if s >= pass_line) * 100 / total, 2),
                'low_score_rate': round(sum(1 for s in valid_scores if s <= low_line) * 100 / total, 2)
            }
        except Exception as e:
            logger.error(f"计算比率失败: error={str(e)}")
            return {
                'excellent_rate': 0,
                'pass_rate': 0,
                'low_score_rate': 0
            }

    def _calculate_school_distribution(self, scores):
        """计算学校分布
        Args:
            scores: QuerySet of ScoreStudentBasic
        Returns:
            dict: {school_name: {count, mean_score, max_score, ...}}
        """
        try:
            distribution = {}

            # 按学校分组统计
            school_stats = scores.values('school_name').annotate(
                count=Count('id'),
                mean_score=Avg('total_score'),
                max_score=Max('total_score'),
                min_score=Min('total_score')
            )

            for stat in school_stats:
                school_scores = scores.filter(
                    school_name=stat['school_name']
                ).values_list('total_score', flat=True)

                # 计算学校的四分位数和比率
                quantiles = self._calculate_quantiles(list(school_scores))
                rates = self._calculate_rates(list(school_scores))

                distribution[stat['school_name']] = {
                    'count': stat['count'],
                    'mean_score': round(float(stat['mean_score'] or 0), 2),
                    'max_score': float(stat['max_score'] or 0),
                    'min_score': float(stat['min_score'] or 0),
                    **quantiles,
                    **rates
                }

            return distribution

        except Exception as e:
            logger.error(f"计算学校分布失败: error={str(e)}")
            return {}

    def _calculate_rank_distribution(self, scores_with_details, group_field='school_name'):
        """计算排名分布
        Args:
            scores_with_details: 包含成绩数据的记录列表
            group_field: 分组字段名称（默认为school_name）
        Returns:
            排名分布统计字典
        """
        try:
            if not scores_with_details:
                logger.warning("没有成绩数据")
                return {}

            exam_id = scores_with_details[0]['exam_id']
            select_type = scores_with_details[0]['select_type']

            # 获取对应科目类型的排名配置
            config = ExamLevelAnalysisConfig.objects.filter(
                exam_id=exam_id,
                select_type=select_type,  # 根据科目类型筛选
                is_active=True
            ).first()

            # 统一使用数字列表格式
            if not config:
                logger.warning(f"未找到排名配置: exam_id={exam_id}, select_type={select_type}, 使用默认配置")
                rank_points = [10, 50, 100, 200, 500, 1000, 3000, 9600]
            else:
                # 解析配置的排名点
                rank_ranges = config.rank_ranges
                if isinstance(rank_ranges, dict) and "市级" in rank_ranges:
                    rank_points = rank_ranges["市级"]
                else:
                    rank_points = rank_ranges if isinstance(rank_ranges, list) else [10, 50, 100, 200, 500, 1000]

                if not rank_points:
                    logger.warning("配置的排名点无效，使用默认配置")
                    rank_points = [10, 50, 100, 200, 500, 1000]

            logger.info(f"使用的排名点配置: {rank_points}")



            # 初始化分组排名统计
            group_rank_counts = {}

            # 按总分、数学、语文排序
            sorted_records = sorted(
                scores_with_details,
                key=lambda x: (float(x['total_score']), float(x['math']), float(x['chinese'])),
                reverse=True
            )
            # 修改排名点的格式
            rank_points_dict = {f'top_{n}': n for n in rank_points}
            # 计算排名
            current_rank = 1
            i = 0
            while i < len(sorted_records):
                current_record = sorted_records[i]
                current_score = float(current_record['total_score'])
                current_math = float(current_record['math'])
                current_chinese = float(current_record['chinese'])
                current_group = current_record[group_field]

                # 找到所有同分的记录
                same_rank_count = 1
                j = i + 1
                while j < len(sorted_records):
                    next_record = sorted_records[j]
                    if (float(next_record['total_score']) == current_score and
                            float(next_record['math']) == current_math and
                            float(next_record['chinese']) == current_chinese):
                        same_rank_count += 1
                        j += 1
                    else:
                        break

                # 初始化当前组的排名统计
                if current_group not in group_rank_counts:
                    group_rank_counts[current_group] = {
                        rank_key: 0 for rank_key in rank_points_dict
                    }

                # 更新排名计数
                for rank_key, rank_threshold in rank_points_dict.items():
                    if int(current_rank) <= int(rank_threshold):
                        group_rank_counts[current_group][rank_key] += 1

                # 处理同分的其他记录
                for k in range(i + 1, i + same_rank_count):
                    group = sorted_records[k][group_field]
                    if group not in group_rank_counts:
                        group_rank_counts[group] = {
                            rank_key: 0 for rank_key in rank_points_dict
                        }
                    for rank_key, rank_threshold in rank_points_dict.items():
                        if current_rank <= rank_threshold:
                            group_rank_counts[group][rank_key] += 1

                # 更新索引和排名
                i += same_rank_count
                current_rank += same_rank_count

            # 只保留有排名的组
            return {
                group: ranks
                for group, ranks in group_rank_counts.items()
                if any(ranks.values())
            }

        except Exception as e:
            logger.error(f"计算排名分布失败: {str(e)}")
            logger.exception(e)
            raise

    def _calculate_threshold_stats(self, scores):
        """计算分数线达线情况"""
        try:
            if not scores.exists():
                logger.warning("没有成绩数据")
                return {}

            exam_id = scores.first().exam_id
            select_type = scores.first().select_type

            # 从配置表获取分数线配置
            config = ExamLevelAnalysisConfig.objects.filter(
                exam_id=exam_id,
                select_type=select_type,
                is_active=True
            ).first()

            if not config:
                logger.warning(f"未找到分数线配置: exam_id={exam_id}, select_type={select_type}")
                return {}

            # 解析分数线配置
            score_lines = config.score_lines
            if select_type in ['文科', '理科']:
                # 分科考试使用固定分数线
                stats = {}
                total_count = scores.filter(total_score__gt=0).count()

                for line_type, line_score in score_lines.items():
                    above_count = scores.filter(
                        total_score__gt=0,
                        total_score__gte=line_score
                    ).count()

                    stats[line_type] = {
                        'score': float(line_score),
                        'count': above_count,
                        'rate': round(above_count * 100 / total_count, 2) if total_count > 0 else 0
                    }
            else:
                # 未分科使用分位数
                scores_array = np.array([float(s.total_score) for s in scores.filter(total_score__gt=0)])
                total_count = len(scores_array)

                if total_count > 0:
                    # 计算分位数
                    q80_score = float(np.percentile(scores_array, 80))
                    q20_score = float(np.percentile(scores_array, 20))
                    q10_score = float(np.percentile(scores_array, 10))

                    # 计算达线人数
                    excellent_count = len(scores_array[scores_array >= q80_score])
                    pass_count = len(scores_array[scores_array >= q20_score])
                    low_count = len(scores_array[scores_array <= q10_score])

                    stats = {
                        'excellent': {
                            'score': q80_score,
                            'count': excellent_count,
                            'rate': round(excellent_count * 100 / total_count, 2)
                        },
                        'pass': {
                            'score': q20_score,
                            'count': pass_count,
                            'rate': round(pass_count * 100 / total_count, 2)
                        },
                        'low': {
                            'score': q10_score,
                            'count': low_count,
                            'rate': round(low_count * 100 / total_count, 2)
                        }
                    }

            logger.info(f"计算的分数线统计: {stats}")
            return stats

        except Exception as e:
            logger.error(f"计算分数线统计失败: error={str(e)}")
            logger.exception(e)
            return {}
    def _calculate_group_distribution(self, scores_with_details, group_field='school_name'):
        """计算分组分布统计（学校或区县）
        Args:
            scores_with_details: 包含详细信息的成绩记录
            group_field: 分组字段名称
        Returns:
            分组统计结果字典
        """
        try:
            # 使用 defaultdict 来收集每个分组的成绩

            scores_by_group = defaultdict(list)

            # 收集每个分组的所有成绩
            for record in scores_with_details:
                group_name = record[group_field]
                scores_by_group[group_name].append(float(record['total_score']))

            # 计算每个分组的统计数据
            distribution = {}
            for group_name, scores in scores_by_group.items():
                scores_array = np.array(scores)
                distribution[group_name] = {
                    'student_count': len(scores),
                    'avg_score': float(np.mean(scores_array)),
                    'max_score': float(np.max(scores_array)),
                    'min_score': float(np.min(scores_array))
                }

            return distribution

        except Exception as e:
            logger.error(f"计算分组分布失败: {str(e)}")
            logger.exception(e)
            raise