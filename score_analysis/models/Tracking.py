# tracking/models.py

from django.db import models
from django.utils import timezone


class TrackingGroup(models.Model):
    """跟踪分组"""
    SCHOOL_LEVEL_CHOICES = [
        ('H', '高中'),
        ('M', '初中'),
        ('P', '小学'),
    ]

    group_name = models.CharField('分组名称', max_length=50)
    school_level = models.CharField('学段', max_length=1, choices=SCHOOL_LEVEL_CHOICES)
    grade_level = models.CharField('年级', max_length=10)  # 如：2025
    layer_type = models.CharField('分层类型', max_length=20)  # 如：尖子生、优分层临界
    score_range = models.CharField('分数线范围', max_length=20, null=True, blank=True)
    description = models.TextField('描述', null=True, blank=True)
    create_time = models.DateTimeField('创建时间', default=timezone.now)
    update_time = models.DateTimeField('更新时间', auto_now=True)
    status = models.BooleanField('启用状态', default=True)

    class Meta:
        db_table = 'tracking_groups'
        verbose_name = '跟踪分组'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['grade_level']),
            models.Index(fields=['school_level']),
        ]


class TrackingStudent(models.Model):
    """跟踪学生"""
    group = models.ForeignKey(TrackingGroup, on_delete=models.CASCADE, verbose_name='所属分组')
    student_id = models.CharField('学生ID', max_length=50)
    student_name = models.CharField('学生姓名', max_length=50)
    class_name = models.CharField('班级名称', max_length=50)
    entry_score = models.DecimalField('入组成绩', max_digits=5, decimal_places=2, null=True)
    entry_rank = models.IntegerField('入组排名', null=True)
    entry_exam_id = models.CharField('入组考试', max_length=50)
    entry_time = models.DateTimeField('入组时间', default=timezone.now)
    exit_time = models.DateTimeField('退出时间', null=True, blank=True)
    status = models.BooleanField('跟踪状态', default=True)

    class Meta:
        db_table = 'tracking_students'
        verbose_name = '跟踪学生'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['student_id']),
            models.Index(fields=['group']),
        ]


class TrackingExam(models.Model):
    """跟踪考试"""
    group = models.ForeignKey(TrackingGroup, on_delete=models.CASCADE, verbose_name='关联分组')
    exam_id = models.CharField('考试ID', max_length=50)
    exam_date = models.DateField('考试日期')
    status = models.BooleanField('跟踪状态', default=True)

    class Meta:
        db_table = 'tracking_exams'
        verbose_name = '跟踪考试'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['exam_id']),
            models.Index(fields=['group']),
        ]


class TrackingRecord(models.Model):
    """跟踪记录"""
    student_id = models.CharField('学生ID', max_length=50)
    exam_id = models.CharField('考试ID', max_length=50)
    total_score = models.DecimalField('总分', max_digits=5, decimal_places=2)
    city_rank = models.IntegerField('市级排名')  # 修改为市级排名
    district_rank = models.IntegerField('区县排名', null=True)  # 修改为区县排名
    school_rank = models.IntegerField('校级排名', null=True)  # 修改为校级排名
    subject_scores = models.JSONField('各科成绩', null=True)
    subject_ranks = models.JSONField('各科排名', null=True)
    improvement = models.DecimalField('进步分数', max_digits=5, decimal_places=2, null=True)
    percentile = models.DecimalField('超越率', max_digits=5, decimal_places=2, null=True)
    create_time = models.DateTimeField('创建时间', default=timezone.now)

    class Meta:
        db_table = 'tracking_records'
        verbose_name = '跟踪记录'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['student_id', 'exam_id']),
        ]

class TrackingAnalysis(models.Model):
    """跟踪分析"""
    student_id = models.CharField('学生ID', max_length=50)
    exam_id = models.CharField('考试ID', max_length=50)
    stability_score = models.DecimalField('稳定性得分', max_digits=5, decimal_places=2, null=True)
    trend_direction = models.SmallIntegerField('趋势', null=True)  # -1下降/0稳定/1上升
    subject_strength = models.JSONField('学科优势', null=True)
    improvement_rate = models.DecimalField('进步率', max_digits=5, decimal_places=2, null=True)
    analysis_time = models.DateTimeField('分析时间', default=timezone.now)

    class Meta:
        db_table = 'tracking_analysis'
        verbose_name = '跟踪分析'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['student_id', 'exam_id']),
        ]


class TrackingTarget(models.Model):
    """跟踪目标"""
    student_id = models.CharField('学生ID', max_length=50)
    target_type = models.CharField('目标类型', max_length=20)  # 总分/单科/排名等
    target_value = models.DecimalField('目标值', max_digits=5, decimal_places=2)
    start_exam_id = models.CharField('起始考试', max_length=50)
    end_exam_id = models.CharField('结束考试', max_length=50, null=True)
    achievement_rate = models.DecimalField('达成率', max_digits=5, decimal_places=2, null=True)
    status = models.BooleanField('达成状态', default=False)
    create_time = models.DateTimeField('创建时间', default=timezone.now)

    class Meta:
        db_table = 'tracking_targets'
        verbose_name = '跟踪目标'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['student_id']),
        ]