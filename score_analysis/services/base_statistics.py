from django.db import models
from django.db.models import Avg, StdDev, Count, Min, Max
from ..models.source import ScoreStudentBasic
from ..models.statistics import StatisticsExamIndicators,ExamScoreLines


class BaseStatisticsService:
    """基础统计服务类，提供共通的统计功能"""

    def calculate_basic_stats(self, exam_id, subject_id=None, stream_type=None, level_type='city'):
        """计算基础统计指标

        Args:
            exam_id: 考试ID
            subject_id: 科目ID，为None时统计总分
            stream_type: 文理科类型，为None时不区分文理科
            level_type: 统计层级，默认city级别

        Returns:
            dict: 包含统计指标的字典
        """
        # 构建查询条件
        query = ScoreStudentBasic.objects.filter(exam_id=exam_id)
        if stream_type:
            query = query.filter(select_type=stream_type)

        # 确定统计字段
        score_field = 'total_score' if not subject_id else subject_id

        # 计算基础统计量
        stats = query.aggregate(
            mean=Avg(score_field),
            std_dev=StdDev(score_field),
            max_score=Max(score_field),
            min_score=Min(score_field),
            student_count=Count('student_id')
        )

        return stats

    def calculate_threshold_stats(self, exam_id, stream_type):
        """计算分数线达成情况

        Args:
            exam_id: 考试ID
            stream_type: 文理科类型

        Returns:
            dict: 包含各分数线达成情况的字典
        """

        # 获取分数线
        score_lines = ExamScoreLines.objects.filter(
            exam_id=exam_id,
            stream_type=stream_type
        )

        # 获取成绩数据
        scores = ScoreStudentBasic.objects.filter(
            exam_id=exam_id,
            select_type=stream_type
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

    def calculate_rankings(self, exam_id, stream_type, level_type):
        """计算排名相关统计

        Args:
            exam_id: 考试ID
            stream_type: 文理科类型
            level_type: 统计层级

        Returns:
            dict: 包含排名统计的字典
        """
        # 获取成绩数据
        scores = ScoreStudentBasic.objects.filter(
            exam_id=exam_id,
            select_type=stream_type
        ).order_by('-total_score')

        # 计算关键名次的分数
        ranking_stats = {}
        total_students = scores.count()

        # 计算特定名次的最低分
        key_ranks = [10, 50, 100, 200, 1250]
        for rank in key_ranks:
            if total_students >= rank:
                score_at_rank = scores[rank - 1].total_score
                ranking_stats[f'top_{rank}_score'] = score_at_rank
            else:
                ranking_stats[f'top_{rank}_score'] = None

        # 计算学校分布
        if level_type == 'school':
            school_stats = scores.values('school_name').annotate(
                student_count=Count('student_id'),
                avg_score=Avg('total_score')
            ).order_by('-avg_score')
            ranking_stats['school_distribution'] = list(school_stats)

        return ranking_stats

    def update_statistics(self, exam_id, subject_id=None, stream_type=None, level_type='city'):
        """更新统计数据到statistics_exam_indicators表

        Args:
            exam_id: 考试ID
            subject_id: 科目ID
            stream_type: 文理科类型
            level_type: 统计层级
        """
        # 计算所有统计指标
        basic_stats = self.calculate_basic_stats(exam_id, subject_id, stream_type, level_type)
        threshold_stats = self.calculate_threshold_stats(exam_id, stream_type)
        ranking_stats = self.calculate_rankings(exam_id, stream_type, level_type)

        # 更新或创建统计记录
        stat_record, created = StatisticsExamIndicators.objects.update_or_create(
            exam_id=exam_id,
            subject_id=subject_id,
            stream_type=stream_type,
            level_type=level_type,
            defaults={
                'mean_score': basic_stats['mean'],
                'std_dev': basic_stats['std_dev'],
                'threshold_stats': threshold_stats,
                **{k: v for k, v in ranking_stats.items() if k.startswith('top_')},
                'school_distribution': ranking_stats.get('school_distribution')
            }
        )

        return stat_record

