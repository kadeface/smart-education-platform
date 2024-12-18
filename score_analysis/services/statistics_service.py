import logging
from django.contrib import messages

from django.db import transaction
from django.db.models import Avg, Max, Min, StdDev, Count, Q
from ..models.base import BaseSubjectConfig
from ..models.statistics import (
    StatisticsExamIndicators,
    ScoreRankings,
    ExamScoreLines
)
from ..models.source import ScoreStudentBasic
import json
logger = logging.getLogger('django')  # 使用Django的默认logger
#from score_processor.models import BaseExamConfig,BaseSubjectConfig
class BaseStatisticsService:
    """基础统计服务"""

    def calculate_basic_statistics(self, exam_id, select_type, level_type='city'):
        """计算统计数据"""
        try:
            logger.info(f"开始计算{select_type}统计数据: exam_id={exam_id}, level_type={level_type}")

            # 基础查询
            scores = ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            )

            # 打印查询条件和SQL
            logger.info(f"查询条件: exam_id={exam_id}, select_type={select_type}")
            logger.info(f"SQL查询: {scores.query}")

            # 检查数据库中是否存在相关记录
            sample_data = ScoreStudentBasic.objects.filter(exam_id=exam_id).values('select_type').distinct()
            logger.info(f"该考试ID下的所有select_type: {list(sample_data)}")

            # 解析考试ID获取考试级别
            exam_parts = exam_id.split('-')
            exam_level = exam_parts[1].upper()

            # 定义统计函数，避免代码重复
            def calculate_stats(scores_data):
                return {
                    'basic_stats': self._calculate_basic_stats(scores_data),
                    'school_count': scores_data.values('school_name').distinct().count(),
                    'quantile_stats': self._calculate_quantile_stats(scores_data),
                    'subject_stats': self._calculate_subject_stats(scores_data, select_type),
                    'threshold_stats': self._calculate_threshold_stats(scores_data),
                    #'school_distribution': self._calculate_school_distribution(scores_data)
                }

            if exam_level == 'CITY':
                # 市级考试：计算市级和区县级统计
                logger.info(f"计算市级{select_type}整体统计")

                # 检查市级数据
                logger.info(f"市级成绩记录数: {scores.count()}")

                # 1. 计算市级统计
                city_stats = calculate_stats(scores)

                # 2. 计算区县统计
                districts = scores.values_list('district_name', flat=True).distinct()
                logger.info(f"发现的区县列表: {list(districts)}")

                district_stats = {}
                for district_name in districts:
                    logger.info(f"计算区县 {district_name} 的{select_type}统计")
                    district_scores = scores.filter(district_name=district_name)
                    logger.info(f"区县 {district_name} 的成绩记录数: {district_scores.count()}")
                    district_stats[district_name] = calculate_stats(district_scores)

                return {
                    'city': city_stats,
                    'districts': district_stats
                }

            else:  # DIST 考试
                # 区县考试：只计算当前区县统计
                logger.info(f"计算区县考试{select_type}统计")

                # 从成绩表中获取区县名称
                actual_district = ScoreStudentBasic.objects.filter(
                    exam_id=exam_id
                ).values_list('district_name', flat=True).distinct().first()

                if not actual_district:
                    raise ValueError(f"未能从成绩表中获取区县信息: {exam_id}")

                logger.info(f"从成绩表中获取到区县: {actual_district}")

                # 使用区县名称查询
                scores = scores.filter(district_name=actual_district)
                logger.info(f"区县成绩记录数: {scores.count()}")

                # 检查是否有数据
                if scores.count() == 0:
                    # 检查原始数据
                    all_records = ScoreStudentBasic.objects.filter(exam_id=exam_id)
                    logger.info(f"该考试ID下的总记录数: {all_records.count()}")
                    if all_records.exists():
                        sample = all_records.first()
                        logger.info(f"示例记录: exam_id={sample.exam_id}, "
                                    f"district_name={sample.district_name}, "
                                    f"select_type={sample.select_type}")
                    else:
                        logger.warning(f"未找到任何相关考试记录: {exam_id}")

                stats = calculate_stats(scores)
                return {actual_district: stats}

        except Exception as e:
            logger.error(
                f"计算统计数据失败: exam_id={exam_id}, select_type={select_type}, level_type={level_type}, error={str(e)}")
            logger.exception("详细错误信息:")
            raise

    def _calculate_basic_stats(self, scores):
        """计算基本统计指标"""
        try:
            stats = scores.aggregate(
                student_count=Count('student_id'),
                max_score=Max('total_score'),
                min_score=Min('total_score'),
                mean=Avg('total_score'),
                std_dev=StdDev('total_score')
            )
            return {
                'student_count': stats['student_count'],
                'max_score': float(stats['max_score']) if stats['max_score'] else 0,
                'min_score': float(stats['min_score']) if stats['min_score'] else 0,
                'mean': float(stats['mean']) if stats['mean'] else 0,
                'std_dev': float(stats['std_dev']) if stats['std_dev'] else 0
            }
        except Exception as e:
            logger.error(f"计算基础统计失败: error={str(e)}")
            raise

    def _calculate_rank_distribution(self, rankings, subject, district_name=None):
        """计算单个科目的排名分布
        Args:
            rankings: 排名数据
            subject: 科目（'total_score'/'chinese'/'math' 等）
            district_name: 区县名称，如果提供则只统计该区县的排名
        Returns:
            dict: {
                'school_rankings': {
                    '学校A': {'top_10': 3, 'top_20': 5, ...},
                    '学校B': {'top_10': 2, 'top_20': 4, ...},
                }
            }
        """
        try:
            # 根据科目选择合适的排名范围
            rank_ranges = {
                'top_10': 10,
                'top_20': 20,
                'top_50': 50,
                'top_100': 100
            }

            # 总分增加更多范围
            if subject == 'total_score':
                rank_ranges.update({
                    'top_200': 200,
                    'top_500': 500,
                    'top_1250': 1250
                })

            # 如果指定了区县，添加level_type过滤条件
            if district_name:
                logger.info(f"计算{district_name}的{subject}排名分布")
                rankings = rankings.filter(level_type=district_name)

            # 初始化学校排名统计
            school_rankings = {}

            # 获取所有符合条件的学生记录
            students = rankings.filter(
                subject=subject,
                raw_score__gt=0,  # 添加这个条件过滤零分
                raw_score_rank__lte=max(rank_ranges.values())  # 只获取最大范围内的记录
            ).values('school_name', 'raw_score_rank')

            # 统计每个学校在各个范围的人数
            for student in students:
                school_name = student.get('school_name')
                rank = student.get('raw_score_rank')

                if not school_name:
                    continue

                # 初始化学校数据
                if school_name not in school_rankings:
                    school_rankings[school_name] = {f'top_{n}': 0 for n in rank_ranges.values()}

                # 更新各个范围的计数
                for range_name, rank_limit in rank_ranges.items():
                    if rank <= rank_limit:
                        school_rankings[school_name][range_name] += 1

            logger.info(f"计算{subject}排名分布成功")
            return school_rankings

        except Exception as e:
            logger.error(f"计算{subject}排名分布失败: error={str(e)}")
            logger.error(f"rankings 数据: {rankings.query}")
            raise

    def _calculate_threshold_stats(self, scores):

        """计算达线统计"""
        try:
            # 获取第一条记录
            first_score = scores.first()
            if not first_score:
                return {}

            # 使用 select_type 字段
            score_lines = ExamScoreLines.objects.filter(
                exam_id=first_score.exam_id,
                select_type=first_score.select_type
            )

            threshold_stats = {}
            for line in score_lines:
                above_count = scores.filter(total_score__gte=line.score).count()
                total_count = scores.count()

                threshold_stats[line.line_type] = {
                    'line': float(line.score),
                    'count': above_count,
                    'rate': round(above_count * 100 / total_count, 2) if total_count > 0 else 0
                }

            return threshold_stats
        except Exception as e:
            logger.error(f"计算达线统计失败: error={str(e)}")
            raise



    def _calculate_subject_quantile_stats(self, scores, subject):
        """计算科目分位数统计"""
        try:
            subject_scores = list(scores.filter(**{
                f'{subject}__isnull': False,
                f'{subject}__gt': 0
            }).values_list(subject, flat=True).order_by(subject))

            if not subject_scores:
                return {
                    'q80': 0,
                    'median': 0,
                    'q20': 0,
                    'q10': 0
                }

            total_count = len(subject_scores)
            return {
                'q80': subject_scores[int(total_count * 0.8)] if total_count > 0 else 0,
                'median': subject_scores[int(total_count * 0.5)] if total_count > 0 else 0,
                'q20': subject_scores[int(total_count * 0.2)] if total_count > 0 else 0,
                'q10': subject_scores[int(total_count * 0.1)] if total_count > 0 else 0
            }
        except Exception as e:
            logger.error(f"计算科目分位数统计失败: subject={subject}, error={str(e)}")
            raise

    def _calculate_subject_school_stats(self, scores, subject):
        """计算科目的学校分布统计"""
        try:
            school_stats = scores.filter(**{
                f'{subject}__isnull': False,
                f'{subject}__gt': 0
            }).values('school_name').annotate(
                count=Count('id'),
                mean=Avg(subject),
                max_score=Max(subject),
                min_score=Min(subject)
            )

            return {
                stat['school_name']: {
                    'count': stat['count'],
                    'mean': round(float(stat['mean']), 2),
                    'max_score': float(stat['max_score']),
                    'min_score': float(stat['min_score'])
                }
                for stat in school_stats
            }
        except Exception as e:
            logger.error(f"计算科目学校分布统计失败: subject={subject}, error={str(e)}")
            raise

    def update_statistics(self, exam_id, select_type, level_type='city'):
        """更新统计数据"""
        try:
            with transaction.atomic():
                # 直接调用 update_subject_statistics 来处理所有科目（包括总分）
                success = self.update_subject_statistics(exam_id, select_type, level_type)
                if success:
                    logger.info(f"统计数据更新成功: exam_id={exam_id}, select_type={select_type}")
                return success
        except Exception as e:
            logger.error(f"更新统计数据失败: exam_id={exam_id}, select_type={select_type}, error={str(e)}")
            return False


    def _prepare_statistics_data(self, stats):
        """准备统计数据"""
        return {
            # 基础统计
            'student_count': stats['basic_stats']['student_count'],
            'max_score': stats['basic_stats']['max_score'],
            'min_score': stats['basic_stats']['min_score'],
            'mean_score': stats['basic_stats']['mean_score'],
            'std_dev': stats['basic_stats']['std_dev'],

            # 分位数统计
            'q80_score': stats['quantile_stats']['q80_score'],
            'median_score': stats['quantile_stats']['median_score'],
            'q20_score': stats['quantile_stats']['q20_score'],
            'q10_score': stats['quantile_stats']['q10_score'],

            # 排名分布
            'top_10_distribution': stats['rank_distribution']['top_10'],
            'top_20_distribution': stats['rank_distribution']['top_20'],
            'top_50_distribution': stats['rank_distribution']['top_50'],
            'top_100_distribution': stats['rank_distribution']['top_100'],
            'top_200_distribution': stats['rank_distribution']['top_200'],
            'top_500_distribution': stats['rank_distribution']['top_500'],
            'top_1250_distribution': stats['rank_distribution']['top_1250'],

            # 其他统计
            'threshold_stats': stats['threshold_stats'],
            'school_distribution': stats['school_distribution'],
            'rank_distribution': stats['rank_distribution'],

            # 等级分布（从threshold_stats计算）
            'excellent_rate': stats['threshold_stats'].get('excellent', {}).get('rate', 0),
            'pass_rate': stats['threshold_stats'].get('pass', {}).get('rate', 0),
            'low_score_rate': stats['threshold_stats'].get('low', {}).get('rate', 0),
        }

    def _calculate_quantile_stats(self, scores):
        """计算分位数统计"""
        try:
            # 首先获取所有分数并排序
            all_scores = list(scores.values_list('total_score', flat=True).order_by('total_score'))

            if not all_scores:
                return {
                    'q80_score': 0,
                    'median_score': 0,
                    'q20_score': 0,
                    'q10_score': 0
                }

            total_count = len(all_scores)

            # 计算各个分位数的索引
            q80_index = int(total_count * 0.8)
            median_index = int(total_count * 0.5)
            q20_index = int(total_count * 0.2)
            q10_index = int(total_count * 0.1)

            return {
                'q80_score': all_scores[q80_index] if q80_index < total_count else all_scores[-1],
                'median_score': all_scores[median_index] if median_index < total_count else all_scores[-1],
                'q20_score': all_scores[q20_index] if q20_index < total_count else all_scores[0],
                'q10_score': all_scores[q10_index] if q10_index < total_count else all_scores[0]
            }
        except Exception as e:
            logger.error(f"计算分位数统计失败: error={str(e)}")
            raise

    def _calculate_subject_stats(self, scores, select_type):
        """计算各科目统计"""
        try:
            # 总分
            subjects = ['total_score']
            subjects.extend(['chinese', 'math', 'english'])

            # 根据文理科添加不同科目
            if select_type == '理科':
                subjects.extend(['physics', 'chemistry', 'biology', 'politics', 'geography'])
            elif select_type == '文科':
                subjects.extend(['history', 'chemistry', 'biology', 'politics', 'geography'])

            logger.info(f"计算{select_type}科目统计: {subjects}")

            # 先打印一下scores的数量
            logger.info(f"总成绩记录数: {scores.count()}")

            # 打印一条示例记录
            sample_score = scores.first()
            if sample_score:
                logger.info(f"示例成绩记录: {sample_score.__dict__}")

            subject_stats = {}
            for subject in subjects:
                field_name = subject
                logger.info(f"开始处理科目 {subject}")

                # 打印该科目的原始数据
                raw_scores = scores.values_list(field_name, flat=True)
                logger.info(f"科目 {subject} 原始成绩数量: {raw_scores.count()}")
                logger.info(f"科目 {subject} 成绩示例: {list(raw_scores[:5])}")

                # 获取该科目的所有分数（排除空值和零分）
                subject_scores = list(scores.values_list(field_name, flat=True)
                                      .exclude(Q(**{field_name: None}) | Q(**{field_name: 0}))
                                      .order_by(field_name))

                if not subject_scores:
                    logger.warning(f"科目 {subject} 没有有效成绩")
                    subject_stats[subject] = {
                        'mean': 0,
                        'max_score': 0,
                        'q80': 0,
                        'median': 0,
                        'q20': 0,
                        'q10': 0
                    }
                    continue

                total_count = len(subject_scores)
                logger.info(f"科目 {subject} 有效成绩数量: {total_count}")

                # 计算分位数索引
                q80_index = int(total_count * 0.8)
                median_index = int(total_count * 0.5)
                q20_index = int(total_count * 0.2)
                q10_index = int(total_count * 0.1)

                # 计算统计值
                stats = scores.aggregate(
                    mean=Avg(field_name),
                    max_score=Max(field_name)
                )

                stats.update({
                    'q80': subject_scores[q80_index] if q80_index < total_count else subject_scores[-1],
                    'median': subject_scores[median_index] if median_index < total_count else subject_scores[-1],
                    'q20': subject_scores[q20_index] if q20_index < total_count else subject_scores[0],
                    'q10': subject_scores[q10_index] if q10_index < total_count else subject_scores[0]
                })
                # 计算该科目的学校分布
                school_stats = scores.values('school_name') \
                    .annotate(
                    count=Count('student_id'),
                    mean=Avg(field_name),
                    max_score=Max(field_name),
                    min_score=Min(field_name),
                    std_dev=StdDev(field_name)
                ) \
                    .values('school_name', 'count', 'mean', 'max_score', 'min_score', 'std_dev')

                # 构建学校分布数据
                school_distribution = {
                    str(stat['school_name']): {
                        'count': stat['count'],
                        'mean': round(float(stat['mean']), 2) if stat['mean'] else 0,
                        'max_score': float(stat['max_score']) if stat['max_score'] else 0,
                        'min_score': float(stat['min_score']) if stat['min_score'] else 0,
                        'std_dev': round(float(stat['std_dev']), 2) if stat['std_dev'] else 0
                    }
                    for stat in school_stats
                }

                # 将所有统计数据合并到一起
                stats.update({
                    'school_distribution': school_distribution
                })

                subject_stats[subject] = stats
                logger.info(f"完成科目 {subject} 统计计算")

            return subject_stats

        except Exception as e:
            logger.error(f"计算科目统计失败: select_type={select_type}, error={str(e)}")
            raise

    def _calculate_single_subject_stats(self, scores, subject):
        """计算单个科目的基础统计"""
        try:
            stats = scores.filter(**{
                f'{subject}__isnull': False,
                f'{subject}__gt': 0
            }).aggregate(
                mean=Avg(subject),
                max_score=Max(subject),
                min_score=Min(subject),
                std_dev=StdDev(subject)
            )
            stats['student_count'] = scores.filter(**{
                f'{subject}__isnull': False,
                f'{subject}__gt': 0
            }).count()
            return stats
        except Exception as e:
            logger.error(f"计算科目基础统计失败: subject={subject}, error={str(e)}")
            raise

    def calculate_subject_statistics(self, exam_id, select_type, subject, level_type='city'):
        """计算单科统计数据"""
        try:
            # 获取成绩数据
            scores = ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            )

            # 计算基础统计
            basic_stats = self._calculate_single_subject_stats(scores, subject)

            # 计算分位数统计
            valid_scores = scores.filter(**{
                f'{subject}__isnull': False,
                f'{subject}__gt': 0
            }).values_list(subject, flat=True).order_by(subject)

            all_scores = list(valid_scores)
            if not all_scores:
                quantile_stats = {
                    'q80_score': 0,
                    'median_score': 0,
                    'q20_score': 0,
                    'q10_score': 0
                }
            else:
                total_count = len(all_scores)
                q80_index = int(total_count * 0.8)
                median_index = int(total_count * 0.5)
                q20_index = int(total_count * 0.2)
                q10_index = int(total_count * 0.1)

                quantile_stats = {
                    'q80_score': float(all_scores[q80_index] if q80_index < total_count else all_scores[-1]),
                    'median_score': float(all_scores[median_index] if median_index < total_count else all_scores[-1]),
                    'q20_score': float(all_scores[q20_index] if q20_index < total_count else all_scores[0]),
                    'q10_score': float(all_scores[q10_index] if q10_index < total_count else all_scores[0])
                }

            # 返回完整的统计数据
            return {
                'basic_stats': {
                    'student_count': basic_stats['student_count'],
                    'max_score': float(basic_stats['max_score']) if basic_stats['max_score'] else 0,
                    'min_score': float(basic_stats['min_score']) if basic_stats['min_score'] else 0,
                    'mean': float(basic_stats['mean']) if basic_stats['mean'] else 0,
                    'std_dev': float(basic_stats['std_dev']) if basic_stats['std_dev'] else 0
                },
                'quantile_stats': quantile_stats,
                'school_distribution': self._calculate_school_distribution(scores)
            }

        except Exception as e:
            logger.error(
                f"计算单科统计数据失败: exam_id={exam_id}, select_type={select_type}, subject={subject}, error={str(e)}")
            raise

    def update_subject_statistics(self, exam_id, select_type, level_type='city'):
        """更新单科统计数据"""
        try:
            # 获取一条记录来判断科目
            sample_score = ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            ).first()

            if not sample_score:
                logger.warning(f"未找到成绩数据: exam_id={exam_id}, select_type={select_type}")
                return False

            # 获取排名数据
            rankings = ScoreRankings.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            )

            # 0. 总分
            subjects = ['total_score']

            # 1. 必考科目（3科）
            subjects.extend(['chinese', 'math', 'english'])

            # 2. 根据文理科添加主科（1科）
            if select_type == '理科':
                subjects.append('physics')
            else:  # 文科
                subjects.append('history')

            # 3. 选考科目（4选2）：从化学、生物、地理、政治中选择大于0的科目
            optional_subjects = ['chemistry', 'biology', 'geography', 'politics']
            for subject in optional_subjects:
                score = getattr(sample_score, subject)
                if score is not None and score > 0:
                    subjects.append(subject)

            # 统计每个科目的数据
            for subject in subjects:
                stats = self._calculate_subject_statistics(exam_id, select_type, subject)
                self._save_subject_statistics(exam_id, select_type, subject, level_type, stats, rankings)

            logger.info(f"单科统计数据更新成功: exam_id={exam_id}, select_type={select_type}")
            return True
        except Exception as e:
            logger.error(f"更新单科统计数据失败: exam_id={exam_id}, select_type={select_type}, error={str(e)}")
            return False


    def _calculate_subject_statistics(self, exam_id, select_type, subject):
        """计算单科统计数据"""
        """计算单科统计数据"""
        try:
            # 获取成绩数据
            scores = ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            )

            # 如果是总分，使用 total_score 字段
            score_field = 'total_score' if subject == 'total_score' else subject

            # 计算基础统计
            if subject == 'total_score':
                basic_stats = scores.aggregate(
                    student_count=Count('student_id'),
                    max_score=Max('total_score'),
                    min_score=Min('total_score'),
                    mean=Avg('total_score'),
                    std_dev=StdDev('total_score')
                )
            else:
                basic_stats = self._calculate_single_subject_stats(scores, subject)

            # 计算分位数统计
            valid_scores = scores.filter(**{
                f'{score_field}__isnull': False,
                f'{score_field}__gt': 0
            }).values_list(score_field, flat=True).order_by(score_field)

            all_scores = list(valid_scores)
            if not all_scores:
                return {
                    'basic_stats': {
                        'student_count': 0,
                        'max_score': 0,
                        'min_score': 0,
                        'mean': 0,
                        'std_dev': 0
                    },
                    'quantile_stats': {
                        'q80_score': 0,
                        'median_score': 0,
                        'q20_score': 0,
                        'q10_score': 0
                    },
                    'school_distribution': {}
                }

            total_count = len(all_scores)
            q80_index = int(total_count * 0.8)
            median_index = int(total_count * 0.5)
            q20_index = int(total_count * 0.2)
            q10_index = int(total_count * 0.1)

            # 返回完整的统计数据
            return {
                'basic_stats': {
                    'student_count': basic_stats['student_count'],
                    'max_score': float(basic_stats['max_score']) if basic_stats['max_score'] else 0,
                    'min_score': float(basic_stats['min_score']) if basic_stats['min_score'] else 0,
                    'mean': float(basic_stats['mean']) if basic_stats['mean'] else 0,
                    'std_dev': float(basic_stats['std_dev']) if basic_stats['std_dev'] else 0
                },
                'quantile_stats': {
                    'q80_score': float(all_scores[q80_index] if q80_index < total_count else all_scores[-1]),
                    'median_score': float(all_scores[median_index] if median_index < total_count else all_scores[-1]),
                    'q20_score': float(all_scores[q20_index] if q20_index < total_count else all_scores[0]),
                    'q10_score': float(all_scores[q10_index] if q10_index < total_count else all_scores[0])
                },
                'school_distribution': self._calculate_school_distribution(scores.filter(**{
                    f'{score_field}__isnull': False,
                    f'{score_field}__gt': 0
                }))
            }

        except Exception as e:
            logger.error(
                f"计算单科统计数据失败: exam_id={exam_id}, select_type={select_type}, subject={subject}, error={str(e)}")
            # 返回默认值
            return {
                'basic_stats': {
                    'student_count': 0,
                    'max_score': 0,
                    'min_score': 0,
                    'mean': 0,
                    'std_dev': 0
                },
                'quantile_stats': {
                    'q80_score': 0,
                    'median_score': 0,
                    'q20_score': 0,
                    'q10_score': 0
                },
                'school_distribution': {}
            }

    def generate_all_statistics(self, exam_id, select_type, level_type='city', request=None):
        """生成所有统计数据的入口方法"""
        try:
            logger.info(f"开始生成{select_type}统计数据: exam_id={exam_id}, level_type={level_type}")

            # 解析考试ID获取考试级别
            exam_parts = exam_id.split('-')
            if len(exam_parts) < 2:
                raise ValueError(f"无效的考试ID格式: {exam_id}")

            exam_level = exam_parts[1].upper()  # CITY 或 DIST
            logger.info(f"考试级别: {exam_level}")

            # 计算统计数据
            stats = self.calculate_basic_statistics(exam_id, select_type, level_type)

            # 获取排名数据
            rankings = ScoreRankings.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            )

            if exam_level == 'CITY':
                # 市级考试：保存市级和区县级统计
                logger.info(f"处理市级考试{select_type}统计")

                # 1. 保存市级统计
                city_stats = stats['city']
                self._save_subject_statistics(
                    exam_id=exam_id,
                    select_type=select_type,
                    level_type='地市级',
                    stats=city_stats,
                    rankings=rankings
                )

                # 2. 保存各区县统计
                district_stats = stats['districts']
                for district_name, district_stat in district_stats.items():
                    logger.info(f"保存区县 {district_name} 的{select_type}统计数据")
                    self._save_subject_statistics(
                        exam_id=exam_id,
                        select_type=select_type,
                        level_type=district_name,
                        stats=district_stat,
                        rankings=rankings
                    )

            else:  # DIST 考试
                # 区县考试：只保存当前区县统计
                # 获取区县名称（stats的键就是区县名称）
                district_name = list(stats.keys())[0]
                district_stats = stats[district_name]

                logger.info(f"处理区县考试{select_type}统计: {district_name}")
                self._save_subject_statistics(
                    exam_id=exam_id,
                    select_type=select_type,
                    level_type=district_name,
                    stats=district_stats,
                    rankings=rankings
                )

            success_msg = f'考试 {exam_id} 的{select_type}统计数据已生成'
            logger.info(success_msg)
            if request:
                messages.success(request, success_msg)
            return True

        except Exception as e:
            error_msg = f"生成{select_type}统计数据失败: exam_id={exam_id}, error={str(e)}"
            logger.error(error_msg)
            logger.exception("详细错误信息:")
            if request:
                messages.error(request, error_msg)
            return False

    def _save_subject_statistics(self, exam_id, select_type, level_type, stats, rankings):
        """保存统计数据"""
        try:
            logger.info(f"开始保存{select_type}统计数据: exam_id={exam_id}, level_type={level_type}")

            # 获取科目统计数据
            subject_stats = stats.get('subject_stats', {})

            # 获取所有科目配置
            subject_configs = {
                subject.subject_id.lower(): subject
                for subject in BaseSubjectConfig.objects.all()
            }

            # 遍历所有科目保存统计数据
            for subject_name, subject_stat in subject_stats.items():
                logger.info(f"保存科目 {subject_name} 的统计数据")

                # 获取科目配置实例
                subject_obj = subject_configs.get(subject_name)
                if not subject_obj:
                    logger.warning(f"未找到科目配置: {subject_name}")
                    continue

                # 获取该科目的排名分布，根据level_type决定是否传入区县名称
                rank_distributions = self._calculate_rank_distribution(
                    rankings=rankings,
                    subject=subject_name,
                    district_name=None if level_type == '地市级' else level_type
                )
                defaults = {
                    # 基础统计
                    'student_count': stats['basic_stats']['student_count'],
                    'max_score': subject_stat['max_score'],
                    'mean_score': subject_stat['mean'],
                    'std_dev': stats['basic_stats'].get('std_dev'),

                    # 分位数统计
                    'q80_score': subject_stat['q80'],
                    'median_score': subject_stat['median'],
                    'q20_score': subject_stat['q20'],
                    'q10_score': subject_stat['q10'],

                    # 学校分布
                    'school_distribution': json.dumps(subject_stat['school_distribution'], ensure_ascii=False),

                    # 排名分布
                    'rank_distribution': json.dumps(rank_distributions, ensure_ascii=False),

                    # 达线统计（如果有的话）
                    'threshold_stats': json.dumps(stats.get('threshold_stats', {}), ensure_ascii=False),

                    # 优秀率、及格率等（如果有的话）
                    'excellent_rate': stats.get('excellent_rate'),
                    'pass_rate': stats.get('pass_rate'),
                    'low_score_rate': stats.get('low_score_rate')
                }

                # 保存或更新统计数据
                StatisticsExamIndicators.objects.update_or_create(
                    exam_id=exam_id,
                    select_type=select_type,
                    subject=subject_obj,
                    level_type=level_type,
                    defaults=defaults
                )

                logger.info(f"完成保存科目 {subject_name} 的统计数据")

            logger.info(f"统计数据保存完成: exam_id={exam_id}, select_type={select_type}")
            return True

        except Exception as e:
            logger.error(f"保存统计数据失败: exam_id={exam_id}, select_type={select_type}, error={str(e)}")
            raise

