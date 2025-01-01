from django.db.models import Avg, Max, Min, Q
from .base import BaseService
from score_analysis.models.Tracking import TrackingStudent, TrackingRecord, TrackingAnalysis,TrackingExam
import statistics
from django.core.cache import cache
from django.db import transaction
from typing import Dict, List, Any, Optional
import numpy as np
from django.utils import timezone

class StudentService(BaseService):
    """学生服务"""

    def get_student_analysis(self, student_id: str) -> Dict[str, Any]:
        """获取学生分析数据"""
        cache_key = self._get_cache_key('student_analysis', student_id)
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

    @transaction.atomic
    def update_student_analysis(self, student_id: str, exam_id: str) -> TrackingAnalysis:
        """更新学生分析数据"""
        student = TrackingStudent.objects.get(student_id=student_id)
        exam = TrackingExam.objects.get(exam_id=exam_id)

        records = TrackingRecord.objects.filter(
            student_id=student_id
        ).order_by('-create_time')

        analysis, created = TrackingAnalysis.objects.update_or_create(
            student=student,
            exam=exam,
            defaults={
                'stability_score': self._calculate_stability(
                    [r.total_score for r in records]
                ),
                'trend_direction': self._get_trend_direction(records),
                'subject_strength': self._analyze_subject_strength(records),
                'improvement_rate': self._calculate_improvement_rate(records)
            }
        )

        return analysis

    def _get_student_info(self, student: TrackingStudent) -> Dict[str, Any]:
        """获取学生基本信息"""
        return {
            'student_id': student.student_id,
            'student_name': student.student_name,
            'class_name': student.class_name,
            'group_name': student.group.group_name,
            'entry_score': float(student.entry_score) if student.entry_score else None,
            'entry_rank': student.entry_rank,
            'tracking_days': (timezone.now() - student.entry_time).days
        }

    def _get_trend_direction(self, records: List[TrackingRecord]) -> int:
        """获取成绩趋势方向"""
        scores = [r.total_score for r in records]
        if len(scores) >= 2:
            x = list(range(len(scores)))
            slope = self._calculate_slope(x, scores)
            return 1 if slope > 0 else (-1 if slope < 0 else 0)
        return 0

    def _analyze_subject_strength(self, records: List[TrackingRecord]) -> Dict[str, Any]:
        """分析学科优势"""
        if not records:
            return {}

        latest = records[0]
        if not latest.subject_scores:
            return {}

        subject_stats = {}
        for subject, score in latest.subject_scores.items():
            subject_scores = [
                r.subject_scores.get(subject)
                for r in records
                if r.subject_scores and subject in r.subject_scores
            ]

            if subject_scores:
                try:
                    avg = np.mean(subject_scores)
                    std = np.std(subject_scores) if len(subject_scores) > 1 else 0
                except:
                    avg = statistics.mean(subject_scores)
                    std = statistics.stdev(subject_scores) if len(subject_scores) > 1 else 0

                subject_stats[subject] = {
                    'current_score': score,
                    'average': round(avg, 2),
                    'stability': round(100 - (std / avg * 100), 2) if avg != 0 else 0,
                    'trend': self._calculate_subject_trend(subject_scores)
                }

        return subject_stats

    def _calculate_improvement_rate(self, records: List[TrackingRecord]) -> float:
        """计算进步率"""
        if len(records) < 2:
            return 0.0

        improvements = [
            r.improvement for r in records
            if r.improvement is not None
        ]

        if not improvements:
            return 0.0

        positive_improvements = sum(1 for imp in improvements if imp > 0)
        return round(positive_improvements / len(improvements) * 100, 2)

    def _calculate_subject_trend(self, scores: List[float]) -> str:
        """计算学科成绩趋势"""
        if len(scores) < 2:
            return 'stable'

        x = list(range(len(scores)))
        slope = self._calculate_slope(x, scores)

        if abs(slope) < 0.1:  # 设置一个阈值来判断是否稳定
            return 'stable'
        return 'up' if slope > 0 else 'down'