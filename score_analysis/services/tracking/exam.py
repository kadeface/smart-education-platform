from django.db.models import Avg, Max, Min, StdDev, Count
from .base import BaseService
from score_analysis.models.Tracking import TrackingExam, TrackingRecord
import statistics
from django.core.cache import cache

class ExamService(BaseService):
    """考试服务"""

    def get_exam_analysis(self, exam_id):
        """获取考试分析"""
        cache_key = self._get_cache_key('exam_analysis', exam_id)
        analysis = cache.get(cache_key)

        if not analysis:
            exam = TrackingExam.objects.get(exam_id=exam_id)
            records = TrackingRecord.objects.filter(exam_id=exam_id)

            analysis = {
                'basic_info': self._get_exam_info(exam),
                'statistics': self._calculate_exam_statistics(records),
                'distribution': self._calculate_score_distribution(records),
                'subjects': self._analyze_exam_subjects(records)
            }
            cache.set(cache_key, analysis, self.cache_timeout)

        return analysis

    def _calculate_exam_statistics(self, records):
        """计算考试统计数据"""
        stats = records.aggregate(
            total_students=Count('id'),
            avg_score=Avg('total_score'),
            max_score=Max('total_score'),
            min_score=Min('total_score'),
            std_dev=StdDev('total_score')
        )

        return {
            'total_students': stats['total_students'],
            'avg_score': round(stats['avg_score'] or 0, 2),
            'max_score': stats['max_score'] or 0,
            'min_score': stats['min_score'] or 0,
            'std_dev': round(stats['std_dev'] or 0, 2),
            'pass_rate': self._calculate_pass_rate(records)
        }

    def _calculate_score_distribution(self, records):
        """计算分数段分布"""
        ranges = [(0, 60), (60, 70), (70, 80), (80, 90), (90, 100), (100, 110), (110, 120), (120, 130), (130, 140), (140, 150)]
        distribution = {}

        for start, end in ranges:
            count = records.filter(
                total_score__gte=start,
                total_score__lt=end
            ).count()
            distribution[f"{start}-{end}"] = count

        return distribution

    def _analyze_exam_subjects(self, records):
        """分析考试各科情况"""
        subject_stats = {}
        for record in records:
            if not record.subject_scores:
                continue
            for subject, score in record.subject_scores.items():
                if subject not in subject_stats:
                    subject_stats[subject] = []
                subject_stats[subject].append(score)

        return {
            subject: {
                'avg': statistics.mean(scores),
                'max': max(scores),
                'min': min(scores),
                'std_dev': statistics.stdev(scores) if len(scores) > 1 else 0
            }
            for subject, scores in subject_stats.items()
            if scores
        }