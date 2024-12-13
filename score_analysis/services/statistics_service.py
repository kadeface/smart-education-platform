import logging
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.admin import ModelAdmin
from django.db import transaction
from django.db.models import Avg, Max, Min, StdDev, Count, F, Window
#from django.db.models.functions import PercentRank, Rank, DenseRank
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
        """计算基础统计数据"""
        try:
            # 基础查询
            scores = ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            )

            rankings = ScoreRankings.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            )

            # 如果是区县级统计
            if level_type == 'district':
                # 获取所有区县
                districts = scores.values_list('district_name', flat=True).distinct()
                district_stats = {}

                # 对每个区县进行统计
                for district in districts:
                    district_scores = scores.filter(district_name=district)
                    district_rankings = rankings.filter(district_name=district)

                    # 获取该区县的学校数量
                    district_school_count = district_scores.values('school_name').distinct().count()

                    # 计算该区县的统计数据
                    district_stats[district] = {
                        'basic_stats': self._calculate_basic_stats(district_scores),
                        'school_count': district_school_count,
                        'quantile_stats': self._calculate_quantile_stats(district_scores),
                        'subject_stats': self._calculate_subject_stats(district_scores, select_type),
                        'rank_distribution': self._calculate_rank_distribution(district_rankings),
                        'threshold_stats': self._calculate_threshold_stats(district_scores),
                        'school_distribution': self._calculate_school_distribution(district_scores)
                    }

                return district_stats

            else:  # 市级统计
                # 获取学校数量
                school_count = scores.values('school_name').distinct().count()

                # 计算市级统计数据
                stats = {
                    'basic_stats': self._calculate_basic_stats(scores),
                    'school_count': school_count,
                    'quantile_stats': self._calculate_quantile_stats(scores),
                    'subject_stats': self._calculate_subject_stats(scores, select_type),
                    'rank_distribution': self._calculate_rank_distribution(rankings),
                    'threshold_stats': self._calculate_threshold_stats(scores),
                    'school_distribution': self._calculate_school_distribution(scores)
                }

                return stats

        except Exception as e:
            logger.error(
                f"计算基础统计数据失败: exam_id={exam_id}, select_type={select_type}, level_type={level_type}, error={str(e)}")
            logger.error(f"详细错误: {str(e)}")  # 添加详细错误信息
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

    def _calculate_rank_distribution(self, rankings,subject):
        """计算单个科目的排名分布
        Args:
            rankings: 排名数据
            subject: 科目（'total_score'/'chinese'/'math' 等）
        """
        try:
            # 根据科目选择合适的排名范围
            if subject == 'total_score':
                # 总分使用全部范围
                rank_ranges = {
                    'top_10': 10,
                    'top_20': 20,
                    'top_50': 50,
                    'top_100': 100,
                    'top_200': 200,
                    'top_500': 500,
                    'top_1250': 1250
                }
            else:
                # 单科目使用较小的范围
                rank_ranges = {
                    'top_10': 10,
                    'top_20': 20,
                    'top_50': 50,
                    'top_100': 100
                }

            distributions = {}
            for range_name, rank_limit in rank_ranges.items():
                # 根据科目筛选排名
                top_students = rankings.filter(
                    raw_score_rank__lte=rank_limit,
                    subject=subject
                )

                # 统计每个学校的人数
                school_counts = {}
                for student in top_students:
                    school_name = student.school_name
                    if school_name:
                        school_counts[school_name] = school_counts.get(school_name, 0) + 1

                # 直接存储学校分布数据
                distributions[range_name] = school_counts

            logger.info(f"计算{subject}排名分布成功: {distributions}")
            return distributions

        except Exception as e:
            logger.error(f"计算{subject}排名分布失败: error={str(e)}")
            logger.error(f"rankings 数据: {rankings.query}")  # 打印查询语句
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

    def _calculate_school_distribution(self, scores):
        """计算学校分布"""
        try:
            school_stats = scores.values('school_name') \
                .annotate(
                count=Count('student_id'),
                mean=Avg('total_score'),
                max_score=Max('total_score'),
                min_score=Min('total_score')
            ) \
                .values('school_name', 'count', 'mean', 'max_score', 'min_score')

            return {
                str(stat['school_name']): {
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
        """计算各科目统计"""
        try:
            # 1. 必考科目（3科）
            subjects = ['chinese', 'math', 'english']

            # 2. 根据文理科添加主科
            if select_type == '理科':
                subjects.append('physics')
            else:  # 文科
                subjects.append('history')

            # 3. 选考科目（4选2）
            optional_subjects = ['chemistry', 'biology', 'geography', 'politics']

            # 获取一条记录来判断选考科目
            sample_score = scores.first()
            if sample_score:
                # 添加有成绩的选考科目
                for subject in optional_subjects:
                    score = getattr(sample_score, subject)
                    if score is not None and score > 0:
                        subjects.append(subject)

            subject_stats = {}
            for subject in subjects:
                field_name = f'{subject}'

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

    def generate_all_statistics(self, request,exam_id, select_type, level_type='city'):
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
    def _save_subject_statistics(self, exam_id, select_type, subject, level_type, stats,rankings):
        """保存单科统计数据"""
        try:
            # 添加调用栈信息
            import traceback
            stack = traceback.extract_stack()
            caller = stack[-2]  # 获取调用者信息
            logger.info(f"保存统计数据被调用: 来自 {caller.filename}:{caller.lineno}, "
                       f"exam_id={exam_id}, select_type={select_type}, subject={subject}")

            # 如果 subject 为空，记录更详细的信息
            if not subject:
                logger.warning(f"尝试保存空 subject_id 的统计数据: "
                             f"exam_id={exam_id}, select_type={select_type}, "
                             f"调用来源={caller.filename}:{caller.lineno}")
                return False
        #    if not subject:
        #        logger.warning(f"跳过保存统计数据: subject_id 为空 (exam_id={exam_id}, select_type={select_type})")
        #        return False
            # 计算排名分布
            rank_distributions = self._calculate_rank_distribution(rankings,subject)
            # 准备保存的数据
            defaults = {
                # 基础统计
                'student_count': stats['basic_stats']['student_count'],
                'max_score': stats['basic_stats']['max_score'],
                'min_score': stats['basic_stats']['min_score'],
                'mean_score': stats['basic_stats']['mean'],
                'std_dev': stats['basic_stats']['std_dev'],
                'rank_distribution': rank_distributions,
                # 分位数统计
                'q80_score': stats['quantile_stats']['q80_score'],
                'median_score': stats['quantile_stats']['median_score'],
                'q20_score': stats['quantile_stats']['q20_score'],
                'q10_score': stats['quantile_stats']['q10_score'],

                # 学校分布
                'school_distribution': json.dumps(stats['school_distribution'], ensure_ascii=False),

                # 排名分布
                'top_10_distribution': rank_distributions.get('top_10', {}),
                'top_20_distribution': rank_distributions.get('top_20', {}),
                'top_50_distribution': rank_distributions.get('top_50', {}),
                'top_100_distribution': rank_distributions.get('top_100', {}),
                'top_200_distribution': rank_distributions.get('top_200', {}),
                'top_500_distribution': rank_distributions.get('top_500', {}),
                'top_1250_distribution': rank_distributions.get('top_1250', {})
            }
            # 使用 update_or_create 来更新或创建记录
            StatisticsExamIndicators.objects.update_or_create(
                exam_id=exam_id,
                subject_id=subject,
                select_type=select_type,
                level_type=level_type,
                defaults=defaults
            )

            logger.info(f"保存单科统计数据成功: exam_id={exam_id}, select_type={select_type}, subject={subject}")
            return True
        except Exception as e:
            logger.error(f"保存单科统计数据失败: exam_id={exam_id}, select_type={select_type}, subject={subject}, error={str(e)}")
            raise


