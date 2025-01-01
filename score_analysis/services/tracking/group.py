from django.db.models import Avg, Max, Min, StdDev, Count, Q
from .base import BaseService
from score_analysis.models.Tracking import TrackingGroup, TrackingRecord
import statistics
from django.core.cache import cache

class GroupService(BaseService):
    """分组服务"""

    def get_group_statistics(self, group_id):
        """获取分组统计信息"""
        cache_key = self._get_cache_key('group_stats', group_id)
        stats = cache.get(cache_key)

        if not stats:
            group = TrackingGroup.objects.get(id=group_id)
            student_ids = group.trackingstudent_set.filter(
                status=True
            ).values_list('student_id', flat=True)

            records = TrackingRecord.objects.filter(student_id__in=student_ids)
            stats = {
                'basic_info': self._get_group_info(group),
                'performance': self._calculate_group_performance(records),
                'trend': self._analyze_group_trend(records),
                'subjects': self._analyze_group_subjects(records)
            }
            cache.set(cache_key, stats, self.cache_timeout)

        return stats

    def _get_group_info(self, group):
        """获取分组基本信息"""
        return {
            'id': group.id,
            'name': group.group_name,
            'school_level': group.get_school_level_display(),
            'grade_level': group.grade_level,
            'student_count': group.trackingstudent_set.filter(status=True).count(),
            'layer_type': group.layer_type
        }

    def _calculate_group_performance(self, records):
        """计算分组整体表现"""
        stats = records.aggregate(
            avg_score=Avg('total_score'),
            max_score=Max('total_score'),
            min_score=Min('total_score'),
            std_dev=StdDev('total_score')
        )
        return {
            'avg_score': round(stats['avg_score'] or 0, 2),
            'max_score': stats['max_score'] or 0,
            'min_score': stats['min_score'] or 0,
            'std_dev': round(stats['std_dev'] or 0, 2)
        }

    def _analyze_group_trend(self, records):
        """分析分组成绩趋势"""
        exam_stats = records.values('exam_id').annotate(
            avg_score=Avg('total_score')
        ).order_by('exam_id')

        scores = [stat['avg_score'] for stat in exam_stats]
        if len(scores) >= 2:
            x = list(range(len(scores)))
            slope = self._calculate_slope(x, scores)
            return {
                'direction': 'up' if slope > 0 else 'down' if slope < 0 else 'stable',
                'slope': round(slope, 2)
            }
        return {'direction': 'insufficient_data', 'slope': 0}

    def _analyze_group_subjects(self, records):
        """分析分组学科情况"""
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
                'stability': self._calculate_stability(scores)
            }
            for subject, scores in subject_stats.items()
            if scores
        }