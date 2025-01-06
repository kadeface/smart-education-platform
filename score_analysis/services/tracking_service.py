from django.db.models import Avg, Max, Min, StdDev, Count, Q
from django.core.cache import cache
from ..models.Tracking import (
    TrackingGroup,
    TrackingStudent,
    TrackingExam,
    TrackingRecord,

)


class TrackingService:
    """跟踪服务统一处理类"""

    def __init__(self):
        self.cache_timeout = 3600  # 缓存时间1小时

    # =============== 分组相关服务 ===============
    def get_group_statistics(self, group_id):
        """获取分组统计信息"""
        cache_key = f'group_stats_{group_id}'
        stats = cache.get(cache_key)

        if not stats:
            group = TrackingGroup.objects.get(id=group_id)
            records = TrackingRecord.objects.filter(
                student_id__in=group.trackingstudent_set.values_list('student_id', flat=True)
            )

            stats = {
                'basic_info': {
                    'group_name': group.group_name,
                    'school_level': group.get_school_level_display(),
                    'grade_level': group.grade_level,
                    'student_count': group.student_count
                },
                'performance': self._calculate_group_performance(records),
                'improvement': self._calculate_group_improvement(group)
            }
            cache.set(cache_key, stats, self.cache_timeout)

        return stats

    def _calculate_group_performance(self, records):
        """计算分组成绩表现"""
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

    # =============== 学生相关服务 ===============
    def get_student_analysis(self, student_id):
        """获取学生分析数据"""
        cache_key = f'student_analysis_{student_id}'
        analysis = cache.get(cache_key)

        if not analysis:
            student = TrackingStudent.objects.get(student_id=student_id)
            records = TrackingRecord.objects.filter(
                student_id=student_id
            ).order_by('-create_time')

            analysis = {
                'basic_info': self._get_student_info(student),
                'performance': self._analyze_student_performance(records),
                'trend': self._analyze_score_trend(records),
                'subjects': self._analyze_subject_performance(records)
            }
            cache.set(cache_key, analysis, self.cache_timeout)

        return analysis

    def _analyze_student_performance(self, records):
        """分析学生成绩表现"""
        latest_record = records.first()
        if not latest_record:
            return {}

        return {
            'latest_score': latest_record.total_score,
            'latest_rank': latest_record.school_rank,
            'improvement': latest_record.improvement,
            'percentile': latest_record.percentile
        }

    # =============== 考试相关服务 ===============
    def get_exam_analysis(self, exam_id):
        """获取考试分析"""
        cache_key = f'exam_analysis_{exam_id}'
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

    # =============== 通用分析方法 ===============
    def _analyze_score_trend(self, records, period=5):
        """分析成绩趋势"""
        records = records[:period]
        scores = [r.total_score for r in records]

        if len(scores) < 2:
            return {'trend': 'insufficient_data'}

        trend = self._calculate_trend(scores)
        return {
            'direction': trend['direction'],
            'slope': trend['slope'],
            'stability': self._calculate_stability(scores)
        }

    def _analyze_subject_performance(self, records, limit=5):
        """分析学科表现"""
        latest_record = records.first()
        if not latest_record or not latest_record.subject_scores:
            return {}

        subjects = latest_record.subject_scores.items()
        return {
            'strong_subjects': self._get_strong_subjects(subjects),
            'weak_subjects': self._get_weak_subjects(subjects),
            'improvement_subjects': self._get_improved_subjects(records[:limit])
        }

    # =============== 辅助方法 ===============
    @staticmethod
    def _calculate_trend(scores):
        """计算趋势"""
        if len(scores) < 2:
            return {'direction': 'stable', 'slope': 0}

        x = list(range(len(scores)))
        slope = TrackingService._calculate_slope(x, scores)

        return {
            'direction': 'up' if slope > 0 else 'down' if slope < 0 else 'stable',
            'slope': round(slope, 2)
        }

    @staticmethod
    def _calculate_slope(x, y):
        """计算线性回归斜率"""
        n = len(x)
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denominator = sum((x[i] - mean_x) ** 2 for i in range(n))

        return numerator / denominator if denominator != 0 else 0