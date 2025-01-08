from django.db.models import Avg,Max,Min,StdDev,Count,Q
from score_analysis.models import BaseExamConfig
from score_analysis.models.statistics import StatisticsExamIndicators
import json
import logging
logger = logging.getLogger(__name__)


class BaseStatisticsService:
    """统计基础服务类"""

    def get_exam_type(self, exam_id):
        """判断考试类型（分科/未分科）
        Returns:
            str: 'division' or 'unified'
        """
        exam_config = BaseExamConfig.objects.get(id=exam_id)
        if exam_config.exam_id.endswith('-H-') and exam_config.semester not in ['高一上']:
            return 'division'
        return 'unified'

    def _format_basic_stats(self, stats):
        """格式化基础统计数据"""
        return {
            'overview': {
                'student_count': stats.student_count,
                'max_score': float(stats.max_score or 0),
                'min_score': float(stats.min_score or 0),
                'mean_score': float(stats.mean_score or 0),
                'std_dev': float(stats.std_dev or 0)
            },
            'rates': {
                'excellent_rate': float(stats.excellent_rate or 0),
                'pass_rate': float(stats.pass_rate or 0),
                'low_score_rate': float(stats.low_score_rate or 0)
            }
        }

    def _format_score_distribution(self, stats):
        """格式化分数分布数据"""
        return {
            'quantiles': {
                'q80': float(stats.q80_score or 0),
                'median': float(stats.median_score or 0),
                'q20': float(stats.q20_score or 0),
                'q10': float(stats.q10_score or 0)
            },
            'threshold_stats': json.loads(stats.threshold_stats) if stats.threshold_stats else {},
            'rank_distribution': json.loads(stats.rank_distribution) if stats.rank_distribution else {}
        }


class ExamStatisticsService(BaseStatisticsService):
    """考试统计服务类"""

    def get_statistics(self, exam_id, level_type='city'):
        """获取考试统计数据
        Args:
            exam_id: 考试ID
            level_type: 统计层级 (city/district/school)
        Returns:
            dict: {
                'type': 'division'/'unified',
                'city_stats': {
                    'unified': {...} 或
                    'arts': {...},
                    'science': {...}
                },
                'district_stats': {  # 仅当level_type为city时
                    'district_1': {
                        'unified': {...} 或
                        'arts': {...},
                        'science': {...}
                    },
                    ...
                }
            }
        """
        try:
            exam_type = self.get_exam_type(exam_id)

            # 获取市级统计
            city_stats = self._get_level_statistics(exam_id, 'city')

            result = {
                'type': exam_type,
                'city_stats': city_stats
            }

            # 如果是市级统计，添加区县数据
            if level_type == 'city':
                district_stats = {}
                districts = self._get_districts(exam_id)

                for district in districts:
                    district_stats[district] = self._get_level_statistics(
                        exam_id, 'district', district_name=district
                    )

                result['district_stats'] = district_stats

            return result

        except Exception as e:
            logger.error(f"获取考试统计失败: exam_id={exam_id}, error={str(e)}")
            logger.exception("详细错误信息:")
            return {}

    def _get_level_statistics(self, exam_id, level_type, district_name=None):
        """获取指定层级的统计数据"""
        # 构建基础查询
        query = StatisticsExamIndicators.objects.filter(
            exam_id=exam_id,
            level_type=level_type
        )

        if district_name:
            query = query.filter(district_name=district_name)

        # 获取总分统计
        total_stats = query.filter(subject__isnull=True)

        # 获取各科统计
        subject_stats = query.filter(subject__isnull=False)

        if self.get_exam_type(exam_id) == 'division':
            return {
                'arts': self._get_stream_statistics(total_stats, subject_stats, '文科'),
                'science': self._get_stream_statistics(total_stats, subject_stats, '理科')
            }
        else:
            return {
                'unified': self._get_stream_statistics(total_stats, subject_stats)
            }

    def _get_stream_statistics(self, total_stats, subject_stats, select_type=None):
        """获取分科/未分科统计数据"""
        if select_type:
            total_stat = total_stats.filter(select_type=select_type).first()
            subjects = subject_stats.filter(select_type=select_type)
        else:
            total_stat = total_stats.first()
            subjects = subject_stats

        if not total_stat:
            return {}

        # 整理统计数据
        result = {
            **self._format_basic_stats(total_stat),
            **self._format_score_distribution(total_stat),
            'subjects': {}
        }

        # 添加各科统计
        for subject in subjects:
            result['subjects'][subject.subject.name] = {
                **self._format_basic_stats(subject),
                **self._format_score_distribution(subject)
            }

        return result

    def _get_districts(self, exam_id):
        """获取考试涉及的区县列表"""
        return StatisticsExamIndicators.objects.filter(
            exam_id=exam_id,
            level_type='district'
        ).values_list('district_name', flat=True).distinct()

    def _calculate_ranking_stats(self, scores):
        """计算排名分布统计

        分科考试：按文理分科分别统计TOP-N排名分布
        未分科考试：统计总体TOP-N排名分布和各分数段的分布
        """
        try:
            if self.select_type in ['文科', '理科']:
                return self._calculate_division_ranking_stats(scores)
            else:
                return self._calculate_undivided_ranking_stats(scores)

        except Exception as e:
            logger.error(f"计算排名分布失败: error={str(e)}")
            return {}

    def _calculate_division_ranking_stats(self, scores):
        """计算分科考试的排名分布"""
        try:
            if not self.rank_ranges:
                return {}

            rank_stats = {}

            # 根据统计层级选择对应的排名字段
            rank_field = {
                'city': 'city_rank',
                'district': 'district_rank',
                'school': 'school_rank'
            }.get(self.level_type, 'city_rank')

            # 按排名字段升序排序
            ranked_scores = scores.filter(**{f"{rank_field}__isnull": False}) \
                .order_by(rank_field)

            for top_n in self.rank_ranges:
                # 获取前N名的成绩
                top_scores = ranked_scores.filter(**{f"{rank_field}__lte": top_n})

                # 统计学校分布
                school_stats = {}
                for score in top_scores:
                    school = score.school_name
                    school_stats[school] = school_stats.get(school, 0) + 1

                # 按人数降序排序
                rank_stats[f'TOP{top_n}'] = {
                    'schools': dict(
                        sorted(
                            school_stats.items(),
                            key=lambda x: x[1],
                            reverse=True
                        )
                    ),
                    'total': sum(school_stats.values()),
                    'avg_score': float(top_scores.aggregate(Avg('total_score'))['total_score__avg'] or 0)
                }

            return rank_stats

        except Exception as e:
            logger.error(f"计算分科排名分布失败: error={str(e)}")
            return {}

    def _calculate_undivided_ranking_stats(self, scores):
        """计算未分科考试的排名分布

        包括：
        1. TOP-N排名分布
        2. 各分数段的学校分布
        3. 优秀生源分布
        """
        try:
            if not self.rank_ranges:
                return {}

            # 根据统计层级选择对应的排名字段
            rank_field = {
                'city': 'city_rank',
                'district': 'district_rank',
                'school': 'school_rank'
            }.get(self.level_type, 'city_rank')

            # 按排名字段升序排序
            ranked_scores = scores.filter(**{f"{rank_field}__isnull": False}) \
                .order_by(rank_field)

            stats = {
                'top_n': {},  # TOP-N排名分布
                'segments': {},  # 分数段分布
                'excellent': {}  # 优秀生源分布
            }

            # 1. 计算TOP-N排名分布
            for top_n in self.rank_ranges:
                top_scores = ranked_scores.filter(**{f"{rank_field}__lte": top_n})

                school_stats = {}
                for score in top_scores:
                    school = score.school_name
                    school_stats[school] = school_stats.get(school, 0) + 1

                stats['top_n'][f'TOP{top_n}'] = {
                    'schools': dict(
                        sorted(
                            school_stats.items(),
                            key=lambda x: x[1],
                            reverse=True
                        )
                    ),
                    'total': sum(school_stats.values()),
                    'avg_score': float(top_scores.aggregate(Avg('total_score'))['total_score__avg'] or 0)
                }

            # 2. 计算分数段分布
            score_segments = [
                (90, None, '90分以上'),
                (80, 90, '80-90分'),
                (70, 80, '70-80分'),
                (60, 70, '60-70分'),
                (None, 60, '60分以下')
            ]

            for min_score, max_score, label in score_segments:
                query = Q()
                if min_score is not None:
                    query &= Q(total_score__gte=min_score)
                if max_score is not None:
                    query &= Q(total_score__lt=max_score)

                segment_scores = scores.filter(query)

                school_stats = {}
                for score in segment_scores:
                    school = score.school_name
                    school_stats[school] = school_stats.get(school, 0) + 1

                stats['segments'][label] = {
                    'schools': dict(
                        sorted(
                            school_stats.items(),
                            key=lambda x: x[1],
                            reverse=True
                        )
                    ),
                    'total': sum(school_stats.values()),
                    'avg_score': float(segment_scores.aggregate(Avg('total_score'))['total_score__avg'] or 0)
                }

            # 3. 计算优秀生源分布（前20%）
            excellent_count = int(ranked_scores.count() * 0.2)
            excellent_scores = ranked_scores[:excellent_count]

            school_stats = {}
            for score in excellent_scores:
                school = score.school_name
                school_stats[school] = school_stats.get(school, 0) + 1

            stats['excellent'] = {
                'schools': dict(
                    sorted(
                        school_stats.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )
                ),
                'total': sum(school_stats.values()),
                'avg_score': float(excellent_scores.aggregate(Avg('total_score'))['total_score__avg'] or 0)
            }

            return stats

        except Exception as e:
            logger.error(f"计算未分科排名分布失败: error={str(e)}")
            return {}

    def _calculate_score_lines(self, scores):
        """计算分数线统计

        分科考试：按设定的分数线统计达线情况
        未分科考试：按比例统计三率及四分位数
        """
        try:
            if self.select_type in ['文科', '理科']:
                return self._calculate_division_score_lines(scores)
            else:
                return self._calculate_undivided_score_lines(scores)

        except Exception as e:
            logger.error(f"计算分数线统计失败: error={str(e)}")
            return {}

    def _calculate_division_score_lines(self, scores):
        """计算分科考试的分数线统计"""
        try:
            if not self.score_lines:
                return {}

            total_count = scores.count()
            if not total_count:
                return {}

            stats = {}
            for line_type, score in self.score_lines.items():
                # 统计达到该分数线的人数
                line_scores = scores.filter(total_score__gte=score)
                count = line_scores.count()

                stats[line_type] = {
                    'line': float(score),
                    'count': count,
                    'rate': round(count * 100 / total_count, 2)
                }

            return stats

        except Exception as e:
            logger.error(f"计算分科分数线统计失败: error={str(e)}")
            return {}

    def _calculate_undivided_score_lines(self, scores):
        """计算未分科考试的统计数据

        包括：
        1. 三率统计（优秀率、合格率、低分率）
        2. 四分位数统计
        3. 平均分及标准差
        """
        try:
            # 获取有效成绩
            valid_scores = scores.filter(total_score__gt=0)
            total_count = valid_scores.count()

            if not total_count:
                return {}

            # 计算基础统计量
            basic_stats = valid_scores.aggregate(
                avg_score=Avg('total_score'),
                std_dev=StdDev('total_score'),
                max_score=Max('total_score'),
                min_score=Min('total_score')
            )

            # 获取排序后的分数列表
            score_list = list(valid_scores.order_by('-total_score')
                              .values_list('total_score', flat=True))

            # 计算四分位数
            q1_pos = int(total_count * 0.25)
            q2_pos = int(total_count * 0.50)
            q3_pos = int(total_count * 0.75)

            quartiles = {
                'Q1': float(score_list[q1_pos]),  # 第一四分位数
                'Q2': float(score_list[q2_pos]),  # 中位数
                'Q3': float(score_list[q3_pos]),  # 第三四分位数
                'IQR': float(score_list[q1_pos] - score_list[q3_pos])  # 四分位距
            }

            # 计算三率
            rates = {}
            for line_type, ratio in self.score_lines.items():
                position = int(total_count * ratio)
                if position >= total_count:
                    position = total_count - 1

                line = float(score_list[position])
                line_scores = valid_scores.filter(total_score__gte=line)
                count = line_scores.count()

                # 计算该分数段的统计数据
                segment_stats = line_scores.aggregate(
                    avg_score=Avg('total_score'),
                    std_dev=StdDev('total_score')
                )

                rates[line_type] = {
                    'ratio': ratio,  # 设置的比例
                    'line': line,  # 计算得出的分数线
                    'count': count,
                    'rate': round(count * 100 / total_count, 2),
                    'avg_score': round(float(segment_stats['avg_score'] or 0), 2),
                    'std_dev': round(float(segment_stats['std_dev'] or 0), 2)
                }

            return {
                'basic_stats': {
                    'avg_score': round(float(basic_stats['avg_score']), 2),
                    'std_dev': round(float(basic_stats['std_dev']), 2),
                    'max_score': float(basic_stats['max_score']),
                    'min_score': float(basic_stats['min_score'])
                },
                'quartiles': quartiles,
                'rates': rates
            }

        except Exception as e:
            logger.error(f"计算未分科统计失败: error={str(e)}")
            return {}