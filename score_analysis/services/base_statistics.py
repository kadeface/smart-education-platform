from django.db import models
from django.db.models import Avg, StdDev, Count, Min, Max, F

from ..models.Tracking import TrackingRecord
#from django.db.models.functions import Percentile
from ..models.source import ScoreStudentBasic
from ..models.statistics import StatisticsExamIndicators, ExamScoreLines,ScoreRankings


class BaseStatisticsService:
    """基础统计服务类，提供共通的统计功能"""

    def calculate_basic_stats(self, exam_id, subject_id=None, select_type=None, level_type='city'):
        """计算基础统计指标，包括四分位数

        Args:
            exam_id: 考试ID
            subject_id: 科目ID，为None时统计总分
            select_type: 文理科类型，为None时不区分文理科
            level_type: 统计层级，默认city级别

        Returns:
            dict: 包含统计指标的字典
        """
        # 构建查询条件
        query = ScoreStudentBasic.objects.filter(exam_id=exam_id)
        if select_type:
            query = query.filter(select_type=select_type)

        # 确定统计字段
        score_field = 'total_score' if not subject_id or subject_id == 'total_score' else subject_id

        # 计算基础统计量
        stats = query.aggregate(
            mean=Avg(score_field),
            std_dev=StdDev(score_field),
            max_score=Max(score_field),
            min_score=Min(score_field),
            student_count=Count('student_id')
        )

        # 计算四分位数
        scores = list(query.values_list(score_field, flat=True).order_by(score_field))
        if scores:
            n = len(scores)
            stats.update({
                'q1': scores[n // 4],  # 第一四分位数
                'q2': scores[n // 2],  # 中位数
                'q3': scores[3 * n // 4],  # 第三四分位数
                'iqr': scores[3 * n // 4] - scores[n // 4]  # 四分位距
            })
        else:
            stats.update({
                'q1': 0,
                'q2': 0,
                'q3': 0,
                'iqr': 0
            })

        # 计算及格率、优秀率和低分率
        total_students = stats['student_count']
        if total_students > 0:
            pass_line = 60
            excellent_line = 90
            low_score_line = 30

            pass_count = query.filter(**{f"{score_field}__gte": pass_line}).count()
            excellent_count = query.filter(**{f"{score_field}__gte": excellent_line}).count()
            low_score_count = query.filter(**{f"{score_field}__lt": low_score_line}).count()

            stats.update({
                'pass_rate': round(pass_count / total_students * 100, 2),
                'excellent_rate': round(excellent_count / total_students * 100, 2),
                'low_score_rate': round(low_score_count / total_students * 100, 2)
            })
        else:
            stats.update({
                'pass_rate': 0,
                'excellent_rate': 0,
                'low_score_rate': 0
            })

        return stats

    def calculate_threshold_stats(self, exam_id, select_type):
        """计算分数线达成情况

        Args:
            exam_id: 考试ID
            select_type: 文理科类型

        Returns:
            dict: 包含各分数线达成情况的字典
        """
        # 获取分数线
        score_lines = ExamScoreLines.objects.filter(
            exam_id=exam_id,
            select_type=select_type
        )

        # 获取成绩数据
        scores = ScoreStudentBasic.objects.filter(
            exam_id=exam_id,
            select_type=select_type
        )

        # 计算达线情况
        threshold_stats = {}
        total_students = scores.count()

        for line in score_lines:
            above_count = scores.filter(
                total_score__gte=line.score
            ).count()

            threshold_stats[line.line_type] = {
                'line': line.score,
                'count': above_count,
                'rate': round(above_count / total_students * 100, 2) if total_students > 0 else 0
            }

        return threshold_stats

    def calculate_rankings(self, exam_id, select_type, level_type):
        """计算排名相关统计，直接使用tracking_records表中的排名信息

        Args:
            exam_id: 考试ID
            select_type: 文理科类型
            level_type: 统计层级 (city/district/school)

        Returns:
            dict: 包含排名统计的字典
        """
        # 根据统计层级选择对应的排名字段
        rank_field = {
            'city': 'city_rank',
            'district': 'district_rank',
            'school': 'school_rank'
        }[level_type]

        # 获取指定考试的所有记录，按选定的排名字段排序
        records = TrackingRecord.objects.filter(
            exam_id=exam_id,
            select_type=select_type
        ).order_by(rank_field)

        # 计算关键名次的分数
        ranking_stats = {}
        total_students = records.count()

        # 计算特定名次的分数线
        key_ranks = [10, 50, 100, 200, 1250, 3000, 9600]
        for rank in key_ranks:
            if total_students >= rank:
                record = records.filter(**{rank_field + '__lte': rank}).order_by(
                    '-' + rank_field
                ).first()

                if record:
                    ranking_stats[f'top_{rank}_score'] = float(record.total_score)
                    ranking_stats[f'top_{rank}_t_score'] = float(record.total_t_score)

                    # 根据层级获取对应的T分
                    t_score_field = {
                        'city': 'city_t_score',
                        'district': 'district_t_score',
                        'school': 'school_t_score'
                    }[level_type]

                    level_t_score = getattr(record, t_score_field)
                    if level_t_score:
                        ranking_stats[f'top_{rank}_level_t_score'] = float(level_t_score)

                    if record.percentile:
                        ranking_stats[f'top_{rank}_percentile'] = float(record.percentile)
            else:
                ranking_stats[f'top_{rank}_score'] = None
                ranking_stats[f'top_{rank}_t_score'] = None
                ranking_stats[f'top_{rank}_level_t_score'] = None
                ranking_stats[f'top_{rank}_percentile'] = None

        # 添加基础统计信息
        if total_students > 0:
            ranking_stats.update({
                'total_students': total_students,
                'max_score': float(records.aggregate(Max('total_score'))['total_score__max']),
                'min_score': float(records.aggregate(Min('total_score'))['total_score__min']),
                'mean_score': float(records.aggregate(Avg('total_score'))['total_score__avg']),
                'max_t_score': float(records.aggregate(Max('total_t_score'))['total_t_score__max']),
                'min_t_score': float(records.aggregate(Min('total_t_score'))['total_t_score__min']),
                'mean_t_score': float(records.aggregate(Avg('total_t_score'))['total_t_score__avg'])
            })

            # 获取对应层级的T分统计
            t_score_field = f'{level_type}_t_score'
            t_score_stats = records.aggregate(
                max_level_t=Max(t_score_field),
                min_level_t=Min(t_score_field),
                avg_level_t=Avg(t_score_field)
            )

            if t_score_stats['max_level_t']:
                ranking_stats.update({
                    f'max_{level_type}_t_score': float(t_score_stats['max_level_t']),
                    f'min_{level_type}_t_score': float(t_score_stats['min_level_t']),
                    f'mean_{level_type}_t_score': float(t_score_stats['avg_level_t'])
                })

        return ranking_stats

    def update_statistics(self, exam_id, subject_id=None, select_type=None, level_type='city'):
        """更新统计数据到statistics_exam_indicators表

        Args:
            exam_id: 考试ID
            subject_id: 科目ID
            select_type: 文理科类型
            level_type: 统计层级
        """
        # 计算所有统计指标
        basic_stats = self.calculate_basic_stats(exam_id, subject_id, select_type, level_type)
        threshold_stats = self.calculate_threshold_stats(exam_id, select_type)
        ranking_stats = self.calculate_rankings(exam_id, select_type, level_type)

        # 更新或创建统计记录
        stat_record, created = StatisticsExamIndicators.objects.update_or_create(
            exam_id=exam_id,
            subject_id=subject_id or 'total_score',
            select_type=select_type,
            level_type=level_type,
            defaults={
                'mean_score': basic_stats['mean'],
                'std_dev': basic_stats['std_dev'],
                'max_score': basic_stats['max_score'],
                'min_score': basic_stats['min_score'],
                'student_count': basic_stats['student_count'],
                'pass_rate': basic_stats['pass_rate'],
                'excellent_rate': basic_stats['excellent_rate'],
                'low_score_rate': basic_stats['low_score_rate'],
                'q1': basic_stats['q1'],  # 第一四分位数
                'q2': basic_stats['q2'],  # 中位数
                'q3': basic_stats['q3'],  # 第三四分位数
                'iqr': basic_stats['iqr'],  # 四分位距
                'threshold_stats': threshold_stats,
                'ranking_stats': ranking_stats
            }
        )

        return stat_record