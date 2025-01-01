from django.db import connection, transaction
from typing import Dict, List, Optional
from .ranking_calculator import RankingCalculator
from .statistics_calculator import StatisticsCalculator
from score_analysis.models.Tracking import  TrackingRecord

class ExamService:
    def __init__(self):
        self.statistics = StatisticsCalculator()
        self.ranking = RankingCalculator(self.statistics)

    def generate_tracking_records(self, exam_id: str) -> int:
        """生成考试跟踪记录
        1. 获取考试原始成绩
        2. 计算统计指标
        3. 计算排名
        4. 生成跟踪记录
        """
        with connection.cursor() as cursor:
            # 1. 获取考试信息和成绩
            cursor.execute("""
                SELECT 
                    e.school_level,
                    e.semester,
                    s.id as student_id,
                    s.student_type,
                    s.class_id,
                    s.grade_id,
                    s.school_id,
                    es.chinese,
                    es.math,
                    es.english,
                    -- ... 其他科目
                FROM exam e
                JOIN exam_score es ON e.id = es.exam_id
                JOIN student s ON es.student_id = s.id
                WHERE e.id = %s
            """, [exam_id])

            columns = [col[0] for col in cursor.description]
            scores = [dict(zip(columns, row)) for row in cursor.fetchall()]

            if not scores:
                return 0

            school_level = scores[0]['school_level']
            semester = scores[0]['semester']

            # 2. 按维度分组计算
            dimensions = ['class_id', 'grade_id', 'school_id']
            records = []

            for score in scores:
                student_id = score['student_id']
                student_type = score['student_type']

                # 获取学生选考科目
                selected_subjects = self.statistics.get_student_optional_subjects(
                    student_id=student_id,
                    semester=semester
                )

                record = {
                    'exam_id': exam_id,
                    'student_id': student_id,
                    'total_score': self.statistics.calculate_total_score(
                        score=score,
                        school_level=school_level,
                        student_type=student_type,
                        selected_subjects=selected_subjects
                    )
                }

                # 计算各维度排名
                for dim in dimensions:
                    # 总分排名
                    record[f'total_rank_{dim}'] = self.ranking.calculate_total_rank(
                        scores=scores,
                        group_by=dim,
                        student_type=student_type,
                        semester=semester
                    ).get(student_id)

                    # 各科排名
                    subjects = self.statistics.get_subjects(
                        school_level=school_level,
                        student_type=student_type
                    )
                    for subject in subjects:
                        if subject in selected_subjects or subject not in ['chemistry', 'biology', 'politics',
                                                                           'geography']:
                            record[f'{subject}_rank_{dim}'] = self.ranking.calculate_subject_rank(
                                scores=scores,
                                subject=subject,
                                group_by=dim,
                                student_type=student_type,
                                semester=semester
                            ).get(student_id)

                # 计算T分
                record['total_t_score'] = self.statistics.calculate_subject_t_scores(
                    scores=scores,
                    subject='total',
                    student_type=student_type,
                    selected_subjects=selected_subjects
                ).get(student_id)

                for subject in subjects:
                    if subject in selected_subjects or subject not in ['chemistry', 'biology', 'politics', 'geography']:
                        record[f'{subject}_t_score'] = self.statistics.calculate_subject_t_scores(
                            scores=scores,
                            subject=subject,
                            student_type=student_type
                        ).get(student_id)

                records.append(record)

            # 4. 批量保存
            with transaction.atomic():
                TrackingRecord.objects.bulk_create(
                    [TrackingRecord(**r) for r in records],
                    update_conflicts=True,
                    unique_fields=['student_id', 'exam_id']
                )

            return len(records)
    def get_exam_statistics(self, exam_id: str) -> Dict:
        """获取考试统计信息"""
        # ... 实现考试统计信息的获取 ...
        pass

    def get_student_tracking(self, student_id: str, semester: str = None) -> List[Dict]:
        """获取学生成绩跟踪"""
        # ... 实现学生成绩跟踪的获取 ...
        pass