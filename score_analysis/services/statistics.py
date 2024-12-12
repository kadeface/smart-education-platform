import logging
from django.db import transaction
from django.db.models import Avg, Max, Min, StdDev, Count, F, Window
#from django.db.models.functions import PercentRank, Rank, DenseRank
from ..models.statistics import (
    StatisticsExamIndicators,
    ScoreRankings,
    ExamScoreLines
)
from ..models.source import ScoreStudentBasic

logger = logging.getLogger('django')  # 使用Django的默认logger
#from score_processor.models import BaseExamConfig,BaseSubjectConfig
class BaseStatisticsService:
    """基础统计服务"""

    def calculate_basic_statistics(self, exam_id, select_type, level_type='city'):
        """计算基础统计数据"""
        try:
            scores = ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            )

            rankings = ScoreRankings.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            )

            # 获取学校数量
            school_count = scores.values('school_id').distinct().count()

            return {
                'basic_stats': self._calculate_basic_stats(scores),
                'school_count': school_count,
                'quantile_stats': self._calculate_quantile_stats(scores),
                'subject_stats': self._calculate_subject_stats(scores, select_type),
                'rank_distribution': self._calculate_rank_distribution(rankings),
                'threshold_stats': self._calculate_threshold_stats(scores),
                'school_distribution': self._calculate_school_distribution(scores)
            }
        except Exception as e:
            logger.error(f"计算基础统计数据失败: exam_id={exam_id}, select_type={select_type}, error={str(e)}")
            raise

    def _calculate_basic_stats(self, scores):
        """计算基本统计指标"""
        try:
            stats = scores.aggregate(
                max_score=Max('total_score'),
                min_score=Min('total_score'),
                mean_score=Avg('total_score'),
                std_dev=StdDev('total_score')
            )
            stats['student_count'] = scores.count()
            return stats
        except Exception as e:
            logger.error(f"计算基本统计指标失败: error={str(e)}")
            raise

    def _calculate_rank_distribution(self, rankings):
        """计算排名分布"""
        try:
            rank_ranges = {
                'top_10': 10,
                'top_20': 20,
                'top_50': 50,
                'top_100': 100,
                'top_200': 200,
                'top_500': 500,
                'top_1250': 1250
            }

            distributions = {}
            for range_name, rank_limit in rank_ranges.items():
                # 获取指定名次范围内的排名记录
                range_rankings = rankings.filter(rank__lte=rank_limit)

                # 按学校统计分布
                school_counts = range_rankings.values('school_id') \
                    .annotate(count=Count('student_id')) \
                    .values('school_id', 'count')

                distributions[range_name] = {
                    str(item['school_id']): item['count']
                    for item in school_counts
                }

            return distributions
        except Exception as e:
            logger.error(f"计算排名分布失败: error={str(e)}")
            raise

    def _calculate_threshold_stats(self, scores):
        """计算达线统计"""
        try:
            score_lines = ExamScoreLines.objects.filter(
                exam_id=scores.first().exam_id,
                select_type=scores.first().select_type
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

    def _calculate_school_distribution(self, scores):
        """计算学校分布"""
        try:
            school_stats = scores.values('school_id') \
                .annotate(
                count=Count('student_id'),
                mean=Avg('total_score'),
                max_score=Max('total_score'),
                min_score=Min('total_score')
            ) \
                .values('school_id', 'count', 'mean', 'max_score', 'min_score')

            return {
                str(stat['school_id']): {
                    'count': stat['count'],
                    'mean': round(float(stat['mean']), 2),
                    'max_score': float(stat['max_score']),
                    'min_score': float(stat['min_score'])
                }
                for stat in school_stats
            }
        except Exception as e:
            logger.error(f"计算学校分布失败: error={str(e)}")
            raise

    def update_statistics(self, exam_id, select_type, level_type='city'):
        """更新统计数据"""
        try:
            with transaction.atomic():
                stats = self.calculate_basic_statistics(exam_id, select_type, level_type)
                self._save_statistics(exam_id, select_type, level_type, stats)
                logger.info(f"统计数据更新成功: exam_id={exam_id}, select_type={select_type}")
                return True
        except Exception as e:
            logger.error(f"更新统计数据失败: exam_id={exam_id}, select_type={select_type}, error={str(e)}")
            return False

    def _save_statistics(self, exam_id, select_type, level_type, stats):
        """保存统计数据"""
        return StatisticsExamIndicators.objects.update_or_create(
            exam_id=exam_id,
            subject_id=None,  # 总分统计
            select_type=select_type,
            level_type=level_type,
            defaults=self._prepare_statistics_data(stats)
        )

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
        """计算各科目统计"""
        try:
            subjects = ['chinese', 'math', 'english']
            if select_type == '理科':
                subjects.extend(['physics', 'chemistry', 'biology'])
            else:  # 文科
                subjects.extend(['politics', 'history', 'geography'])

            subject_stats = {}
            for subject in subjects:
                field_name = f'{subject}_score'

                # 获取该科目的所有分数
                subject_scores = list(scores.values_list(field_name, flat=True).order_by(field_name))

                if not subject_scores:
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

                subject_stats[subject] = stats

            return subject_stats
        except Exception as e:
            logger.error(f"计算科目统计失败: error={str(e)}")
            raise


    def update_subject_statistics(self, exam_id, select_type, level_type='city'):
        """更新单科统计数据"""
        try:
            # 获取科目列表
            subjects = ['chinese', 'math', 'english']
            if select_type == '理科':
                subjects.extend(['physics', 'chemistry', 'biology'])
            else:
                subjects.extend(['politics', 'history', 'geography'])

            for subject in subjects:
                stats = self._calculate_subject_statistics(exam_id, select_type, subject)
                self._save_subject_statistics(exam_id, select_type, subject, level_type, stats)

            logger.info(f"单科统计数据更新成功: exam_id={exam_id}, select_type={select_type}")
            return True
        except Exception as e:
            logger.error(f"更新单科统计数据失败: exam_id={exam_id}, select_type={select_type}, error={str(e)}")
            return False


    def _calculate_subject_statistics(self, exam_id, select_type, subject):
        """计算单科统计数据"""
        score_field = f'{subject}_score'
        scores = ScoreStudentBasic.objects.filter(
            exam_id=exam_id,
            select_type=select_type
        )

        return {
            'basic_stats': self._calculate_subject_basic_stats(scores, score_field),
            'quantile_stats': self._calculate_subject_quantile_stats(scores, score_field),
            'school_distribution': self._calculate_subject_school_stats(scores, score_field)
        }


    def generate_all_statistics(self, exam_id, select_type, level_type='city'):
        """生成所有统计数据"""
        try:
            with transaction.atomic():
                # 1. 更新总分统计
                self.update_statistics(exam_id, select_type, level_type)

                # 2. 更新单科统计
                self.update_subject_statistics(exam_id, select_type, level_type)

                logger.info(f"所有统计数据更新成功: exam_id={exam_id}, select_type={select_type}")
                return True
        except Exception as e:
            logger.error(f"生成统计数据失败: exam_id={exam_id}, select_type={select_type}, error={str(e)}")
            return False