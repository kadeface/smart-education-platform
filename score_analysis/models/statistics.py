# score_analysis/models/statistics.py
from django.db import models
from .base import BaseExamConfig, BaseSubjectConfig

class ScoreRankings(models.Model):
    ranking_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey(BaseExamConfig, models.DO_NOTHING, db_comment='考试ID')
    unified_student_id = models.CharField(max_length=50, db_comment='统一学生ID')
    subject = models.ForeignKey(BaseSubjectConfig, models.DO_NOTHING, db_comment='科目ID')
    stream_type = models.CharField(max_length=10, db_comment='文科/理科/统一')
    level_type = models.CharField(max_length=20, db_comment='分析层级：city/district/school')
    raw_score = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    raw_score_rank = models.IntegerField(null=True)
    total_count = models.IntegerField(null=True, db_comment='总人数')
    percentile = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = 'score_rankings'
        unique_together = (('exam', 'unified_student_id', 'subject', 'stream_type', 'level_type'),)

class ScoreDistributions(models.Model):
    distribution_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey(BaseExamConfig, models.DO_NOTHING, db_comment='考试ID')
    subject = models.ForeignKey(BaseSubjectConfig, models.DO_NOTHING, db_comment='科目ID')
    stream_type = models.CharField(max_length=10, db_comment='文科/理科/统一')
    level_type = models.CharField(max_length=20, db_comment='分析层级：city/district/school')
    score_range = models.CharField(max_length=20, null=True, db_comment='分数段')
    student_count = models.IntegerField(null=True, db_comment='学生数')
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='占比')
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = 'score_distributions'
        indexes = [
            models.Index(fields=['exam', 'subject'], name='idx_dist_exam_subject'),
            models.Index(fields=['level_type', 'stream_type'], name='idx_dist_level_stream'),
        ]
        unique_together = (('exam', 'subject', 'stream_type', 'level_type', 'score_range'),)

class SubjectTScore(models.Model):
    """学科T分表"""
    score_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey(BaseExamConfig, models.DO_NOTHING, db_comment='考试ID')
    unified_student_id = models.CharField(max_length=50, db_comment='统一学生ID')
    subject = models.ForeignKey(BaseSubjectConfig, models.DO_NOTHING, db_comment='科目ID')
    stream_type = models.CharField(max_length=10, db_comment='文科/理科/统一')
    level_type = models.CharField(max_length=20, db_comment='分析层级：city/district/school')
    raw_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='原始分')
    t_score = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    z_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='Z分数')
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = 'subject_t_scores'
        unique_together = (('exam', 'unified_student_id', 'subject', 'stream_type', 'level_type'),)
        indexes = [
            models.Index(fields=['exam', 'unified_student_id'], name='idx_exam_student'),
            models.Index(fields=['subject', 'level_type'], name='idx_subject_level'),
            models.Index(fields=['stream_type', 'level_type'], name='idx_stream_level'),
        ]


class SubjectStatistics(models.Model):
    stat_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey(BaseExamConfig, models.DO_NOTHING, db_comment='考试ID')
    subject = models.ForeignKey(BaseSubjectConfig, models.DO_NOTHING, db_comment='科目ID')
    stream_type = models.CharField(max_length=10, db_comment='文科/理科/统一')
    level_type = models.CharField(max_length=20, db_comment='分析层级：city/district/school')
    sample_size = models.IntegerField(null=True, db_comment='样本量')
    mean = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='原始分平均分')
    std_dev = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='原始分标准差')
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = 'subject_statistics'
        unique_together = (('exam', 'subject', 'stream_type', 'level_type'),)
        indexes = [
            models.Index(fields=['exam', 'level_type'], name='idx_exam_level'),
        ]

