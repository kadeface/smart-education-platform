#from django.db import transaction
#from django.db.models import F, Q, Avg, Count, Max, Min
#from ..models.source import ScoreStudentBasic, ExamSubjectConfig
from .base_statistics import BaseStatisticsService
from ..models.statistics import StatisticsExamTrend
#from score_processor.models import ExamSubjectConfig
from ..models.source import ScoreStudentBasic

class TrendAnalysisService:
    """趋势分析服务类"""

    def __init__(self):
        self.base_service = BaseStatisticsService()

    def analyze_exam_trend(self, current_exam_id, compare_exam_id, stream_type=None, level_type='city'):
        """分析两次考试的趋势

        Args:
            current_exam_id: 当前考试ID
            compare_exam_id: 对比考试ID
            stream_type: 文理科类型，默认None处理所有类型
            level_type: 统计层级，默认city

        Returns:
            dict: 包含趋势分析结果的字典
        """
        try:
            if not stream_type:
                # 获取两次考试共有的文理科类型
                current_streams = set(ScoreStudentBasic.objects.filter(
                    exam_id=current_exam_id
                ).values_list('select_type', flat=True).distinct())

                compare_streams = set(ScoreStudentBasic.objects.filter(
                    exam_id=compare_exam_id
                ).values_list('select_type', flat=True).distinct())

                stream_types = current_streams.intersection(compare_streams)
            else:
                stream_types = {stream_type}

            trend_results = {}
            for stream in stream_types:
                # 分析总分趋势
                total_trend = self._analyze_total_score_trend(
                    current_exam_id, compare_exam_id, stream, level_type
                )

                # 分析学科趋势
                subject_trends = self._analyze_subject_trends(
                    current_exam_id, compare_exam_id, stream, level_type
                )

                trend_results[stream] = {
                    'total': total_trend,
                    'subjects': subject_trends
                }

            return trend_results

        except Exception as e:
            raise Exception(f"分析考试趋势时发生错误: {str(e)}")

    def _analyze_total_score_trend(self, current_exam_id, compare_exam_id, stream_type, level_type):
        """分析总分趋势"""
        # 获取当前考试统计数据
        current_stats = self.base_service.calculate_basic_stats(
            current_exam_id, None, stream_type, level_type
        )

        # 获取对比考试统计数据
        compare_stats = self.base_service.calculate_basic_stats(
            compare_exam_id, None, stream_type, level_type
        )

        # 计算变化
        trend_data = {
            'mean_change': current_stats['mean'] - compare_stats['mean'],
            'mean_change_rate': self._calculate_change_rate(
                current_stats['mean'], compare_stats['mean']
            ),
            'std_dev_change': current_stats['std_dev'] - compare_stats['std_dev']
        }

        # 分析分数段变化
        score_segments = self._analyze_score_segments(
            current_exam_id, compare_exam_id, stream_type
        )
        trend_data['score_segment_changes'] = score_segments

        # 保存趋势分析结果
        trend_record = StatisticsExamTrend.objects.update_or_create(
            current_exam_id=current_exam_id,
            compare_exam_id=compare_exam_id,
            subject_id=None,  # 总分分析
            stream_type=stream_type,
            level_type=level_type,
            defaults=trend_data
        )

        return trend_record[0]

    def _analyze_subject_trends(self, current_exam_id, compare_exam_id, stream_type, level_type):
        """分析学科趋势"""
        from score_processor.models import BaseSubjectConfig

        subject_trends = {}
        subjects = BaseSubjectConfig.objects.all()

        for subject in subjects:
            # 获取当前考试科目统计
            current_stats = self.base_service.calculate_basic_stats(
                current_exam_id, subject.subject_id, stream_type, level_type
            )

            # 获取对比考试科目统计
            compare_stats = self.base_service.calculate_basic_stats(
                compare_exam_id, subject.subject_id, stream_type, level_type
            )

            # 计算变化
            trend_data = {
                'mean_change': current_stats['mean'] - compare_stats['mean'],
                'mean_change_rate': self._calculate_change_rate(
                    current_stats['mean'], compare_stats['mean']
                ),
                'std_dev_change': current_stats['std_dev'] - compare_stats['std_dev']
            }

            # 更新趋势记录
            trend_record = StatisticsExamTrend.objects.update_or_create(
                current_exam_id=current_exam_id,
                compare_exam_id=compare_exam_id,
                subject_id=subject.subject_id,
                stream_type=stream_type,
                level_type=level_type,
                defaults=trend_data
            )

            subject_trends[subject.subject_id] = trend_record[0]

        return subject_trends

    def _analyze_score_segments(self, current_exam_id, compare_exam_id, stream_type):
        """分析分数段变化"""
        # 定义分数段
        segments = [
            {'min': 0, 'max': 300, 'name': '0-300'},
            {'min': 300, 'max': 400, 'name': '300-400'},
            {'min': 400, 'max': 500, 'name': '400-500'},
            {'min': 500, 'max': 600, 'name': '500-600'},
            {'min': 600, 'max': 700, 'name': '600-700'},
            {'min': 700, 'max': 1000, 'name': '700以上'}
        ]

        segment_changes = {}
        for segment in segments:
            # 当前考试该分数段人数
            current_count = ScoreStudentBasic.objects.filter(
                exam_id=current_exam_id,
                select_type=stream_type,
                total_score__gte=segment['min'],
                total_score__lt=segment['max']
            ).count()

            # 对比考试该分数段人数
            compare_count = ScoreStudentBasic.objects.filter(
                exam_id=compare_exam_id,
                select_type=stream_type,
                total_score__gte=segment['min'],
                total_score__lt=segment['max']
            ).count()

            # 计算变化
            segment_changes[segment['name']] = {
                'current_count': current_count,
                'prev_count': compare_count,
                'change_rate': self._calculate_change_rate(current_count, compare_count)
            }

        return segment_changes

    @staticmethod
    def _calculate_change_rate(current_value, previous_value):
        """计算变化率"""
        if previous_value and previous_value != 0:
            return round((current_value - previous_value) / previous_value * 100, 2)
        return 0