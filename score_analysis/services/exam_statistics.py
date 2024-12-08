from django.db import transaction
from django.db.models import F, Q, Avg, Count, Max, Min
from .base_statistics import BaseStatisticsService
from ..models.statistics import StatisticsExamIndicators,ExamScoreLines
from ..models.source import ScoreStudentBasic
from ..models.base import  BaseSubjectConfig

class ExamStatisticsService:
    """考试统计服务类，处理单次考试的统计"""

    def __init__(self):
        self.base_service = BaseStatisticsService()

    def process_exam_statistics(self, exam_id, stream_types=None):
        """处理考试统计主流程

        Args:
            exam_id: 考试ID
            stream_types: 文理科类型列表，默认处理所有类型

        Returns:
            dict: 包含统计结果的字典
        """
        if not stream_types:
            # 获取考试中存在的文理科类型
            stream_types = ScoreStudentBasic.objects.filter(
                exam_id=exam_id
            ).values_list('select_type', flat=True).distinct()

        statistics = {}
        try:
            with transaction.atomic():
                for stream_type in stream_types:
                    # 处理不同层级的统计
                    for level_type in ['city', 'district', 'school']:
                        # 更新总体统计
                        total_stats = self._update_total_statistics(
                            exam_id, stream_type, level_type
                        )

                        # 更新学科统计
                        subject_stats = self._update_subject_statistics(
                            exam_id, stream_type, level_type
                        )

                        statistics[f"{stream_type}_{level_type}"] = {
                            'total': total_stats,
                            'subjects': subject_stats
                        }

            return statistics

        except Exception as e:
            # 记录错误并抛出异常
            raise Exception(f"处理考试统计时发生错误: {str(e)}")

    def _update_total_statistics(self, exam_id, stream_type, level_type):
        """更新总分统计数据"""
        # 使用基础服务计算统计值
        basic_stats = self.base_service.calculate_basic_stats(
            exam_id, None, stream_type, level_type
        )

        # 计算分数线达成情况
        threshold_stats = self.base_service.calculate_threshold_stats(
            exam_id, stream_type
        )

        # 计算排名统计
        ranking_stats = self.base_service.calculate_rankings(
            exam_id, stream_type, level_type
        )

        # 更新到统计表
        indicators = StatisticsExamIndicators.objects.update_or_create(
            exam_id=exam_id,
            subject_id=None,  # 总分统计
            stream_type=stream_type,
            level_type=level_type,
            defaults={
                'mean_score': basic_stats['mean'],
                'std_dev': basic_stats['std_dev'],
                'threshold_stats': threshold_stats,
                **ranking_stats
            }
        )

        return indicators[0]

    def _update_subject_statistics(self, exam_id, stream_type, level_type):
        """更新学科统计数据"""
        from score_processor.models import BaseSubjectConfig

        subject_stats = {}
        # 获取所有科目
        subjects = BaseSubjectConfig.objects.all()

        for subject in subjects:
            # 计算科目统计值
            stats = self.base_service.calculate_basic_stats(
                exam_id, subject.subject_id, stream_type, level_type
            )

            # 更新科目统计记录
            indicators = StatisticsExamIndicators.objects.update_or_create(
                exam_id=exam_id,
                subject_id=subject.subject_id,
                stream_type=stream_type,
                level_type=level_type,
                defaults={
                    'mean_score': stats['mean'],
                    'std_dev': stats['std_dev'],
                    'excellent_rate': self._calculate_excellent_rate(
                        exam_id, subject.subject_id, stream_type
                    ),
                    'pass_rate': self._calculate_pass_rate(
                        exam_id, subject.subject_id, stream_type
                    )
                }
            )

            subject_stats[subject.subject_id] = indicators[0]

        return subject_stats

    def _calculate_excellent_rate(self, exam_id, subject_id, stream_type):
        """计算优秀率"""
        # 获取科目配置
        subject_config = BaseSubjectConfig.objects.get(
            exam_id=exam_id,
            subject_id=subject_id
        )

        # 计算优秀率
        total_count = ScoreStudentBasic.objects.filter(
            exam_id=exam_id,
            select_type=stream_type
        ).count()

        excellent_count = ScoreStudentBasic.objects.filter(
            exam_id=exam_id,
            select_type=stream_type,
            **{f"{subject_id}__gte": subject_config.excellent_score}
        ).count()

        return round(excellent_count / total_count * 100, 2) if total_count > 0 else 0

    def _calculate_pass_rate(self, exam_id, subject_id, stream_type):
        """计算及格率"""


        # 获取科目配置
        subject_config = BaseSubjectConfig.objects.get(
            exam_id=exam_id,
            subject_id=subject_id
        )

        # 计算及格率
        total_count = ScoreStudentBasic.objects.filter(
            exam_id=exam_id,
            select_type=stream_type
        ).count()

        pass_count = ScoreStudentBasic.objects.filter(
            exam_id=exam_id,
            select_type=stream_type,
            **{f"{subject_id}__gte": subject_config.pass_score}
        ).count()

        return round(pass_count / total_count * 100, 2) if total_count > 0 else 0