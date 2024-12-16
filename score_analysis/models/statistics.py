# score_analysis/models/statistics_service.py
from django.db import models
from .base import BaseExamConfig, BaseSubjectConfig
#from django.core.exceptions import ValidationError




class ScoreDistributions(models.Model):
    distribution_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey(BaseExamConfig, models.DO_NOTHING, db_comment='考试ID')
    subject = models.ForeignKey(BaseSubjectConfig, models.DO_NOTHING, db_comment='科目ID')
    select_type = models.CharField(max_length=10, db_comment='文科/理科')
    level_type = models.CharField(max_length=20, db_comment='分析层级：city/district/school')
    score_range = models.CharField(max_length=20, null=True, db_comment='分数段')
    student_count = models.IntegerField(null=True, db_comment='学生数')
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='占比')
    create_time = models.DateTimeField(auto_now_add=True)
    cumulative_count = models.IntegerField(null=True, db_comment='累计人数')
    cumulative_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='累计百分比')
    density = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='区间密度')
    class Meta:
        managed = False
        db_table = 'score_distributions'
        indexes = [
            models.Index(fields=['exam', 'subject'], name='idx_dist_exam_subject'),
            models.Index(fields=['level_type', 'select_type'], name='idx_dist_level_stream'),
        ]
        unique_together = (('exam', 'subject', 'select_type', 'level_type', 'score_range'),)

class SubjectTScore(models.Model):
    """学科T分表"""
    score_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey(BaseExamConfig, models.DO_NOTHING, db_comment='考试ID')
    unified_student_id = models.CharField(max_length=50, db_comment='统一学生ID')
    subject = models.ForeignKey(BaseSubjectConfig, models.DO_NOTHING, db_comment='科目ID')
    select_type = models.CharField(max_length=10, db_comment='文科/理科')
    level_type = models.CharField(max_length=20, db_comment='分析层级：city/district/school')
    raw_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='原始分')
    t_score = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    z_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='Z分数')
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'subject_t_scores'
        unique_together = (('exam', 'unified_student_id', 'subject', 'select_type', 'level_type'),)
        indexes = [
            models.Index(fields=['exam', 'unified_student_id'], name='idx_exam_student'),
            models.Index(fields=['subject', 'level_type'], name='idx_subject_level'),
            models.Index(fields=['select_type', 'level_type'], name='idx_select_level'),
        ]


class SubjectStatistics(models.Model):
    stat_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey(BaseExamConfig, models.DO_NOTHING, db_comment='考试ID')
    subject = models.ForeignKey(BaseSubjectConfig, models.DO_NOTHING, db_comment='科目ID')
    select_type = models.CharField(max_length=10, db_comment='文科/理科')
    level_type = models.CharField(max_length=20, db_comment='分析层级：city/district/school')
    sample_size = models.IntegerField(null=True, db_comment='样本量')
    mean = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='原始分平均分')
    std_dev = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='原始分标准差')
    median = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='中位数')
    q1 = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='第一四分位数')
    q3 = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='第三四分位数')
    iqr = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='四分位距')
    mode = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='众数')
    skewness = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='偏度')
    kurtosis = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='峰度')
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'subject_statistics'
        unique_together = (('exam', 'subject', 'select_type', 'level_type'),)
        indexes = [
            models.Index(fields=['exam', 'level_type'], name='idx_exam_level'),
        ]




class ExamScoreLines(models.Model):
    STREAM_CHOICES = [
        ('文科', '文科'),
        ('理科', '理科'),
    ]
    LINE_TYPE_CHOICES = [
        ('C9层', 'C9层'),
        ('985层', '985层'),
        ('211层', '211层'),
        ('双一流层', '双一流层'),
        ('优分层', '优分层'),
        ('本科层', '本科层'),
    ]
    line_id = models.AutoField(primary_key=True)
    exam_id = models.CharField(max_length=50)
    line_type = models.CharField(
        max_length=20,
        choices=LINE_TYPE_CHOICES,
        help_text='分数线类型:C9层，985层，211层，双一流层，优分层，本科层',
        default='本科层'  # 添加默认值
    )
    select_type = models.CharField(
        max_length=10,
        choices=STREAM_CHOICES,
        help_text='文理分科(文科/理科)',
        default='理科'
    )
    score = models.DecimalField(max_digits=6, decimal_places=2, help_text='分数线值')
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'exam_score_lines'
        unique_together = ['exam_id','select_type', 'line_type']
        verbose_name = '考试分数线'
        verbose_name_plural = '考试分数线'

    def __str__(self):
        return f"{self.exam_id}-{self.select_type}-{self.line_type}"


class StatisticsExamTrend(models.Model):
    """考试趋势分析表"""
    trend_id = models.BigAutoField(primary_key=True)
    current_exam = models.ForeignKey('score_processor.BaseExamConfig', models.DO_NOTHING, related_name='current_exam',
                                     db_comment='当前考试')
    compare_exam = models.ForeignKey('score_processor.BaseExamConfig', models.DO_NOTHING, related_name='compare_exam',
                                     db_comment='对比考试')
    subject = models.ForeignKey('score_processor.BaseSubjectConfig', models.DO_NOTHING, null=True,
                                db_comment='科目(为空表示总分)')
    select_type = models.CharField(max_length=10, db_comment='文科/理科/统一')
    level_type = models.CharField(max_length=20, db_comment='分析层级：city/district/school')

    # 基础对比指标
    mean_change = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='平均分变化')
    mean_change_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='平均分变化率')
    std_dev_change = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='标准差变化')
    score_segment_changes = models.JSONField(null=True, db_comment='分数段人数变化')
    grade_changes = models.JSONField(null=True, db_comment='等级分布变化')
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'statistics_exam_trend'
        unique_together = (('current_exam', 'compare_exam', 'subject', 'select_type', 'level_type'),)


# StatisticsExamIndicators模型的简化版本
class StatisticsExamIndicators(models.Model):
    """考试指标统计表"""
    indicator_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey('score_processor.BaseExamConfig', models.DO_NOTHING, db_comment='考试ID')
    subject = models.ForeignKey('score_processor.BaseSubjectConfig', models.DO_NOTHING, null=True,
                                db_comment='科目')
    select_type = models.CharField(max_length=10, db_comment='文科/理科')
    level_type = models.CharField(max_length=20, db_comment='分析层级：city/district/school')

    # 成绩指标
    excellent_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='优秀率')
    pass_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='及格率')
    low_score_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='低分率')

    # 达线指标
    threshold_stats = models.JSONField(null=True, db_comment='各条线达线统计')  # {line_type: {count, rate}}

    # 学校分布
    school_distribution = models.JSONField(null=True, db_comment='学校分布统计')  # {school_id: {count, rate}}

    # 基础统计指标
    student_count = models.IntegerField(null=True, db_comment='参考人数')
    max_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='最高分')
    min_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='最低分')
    mean_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='平均分')
    std_dev = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='标准差')
    # 四分位数指标
    q80_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='80分位分数')
    median_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='中位数分数')
    q20_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='20分位分数')
    q10_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, db_comment='10分位分数')
    # 排名分布
    rank_distribution = models.JSONField(null=True, db_comment='排名分布统计')  # {school_name: {top_10: n, top_20: n, ...}}
    create_time = models.DateTimeField(auto_now_add=True)

    # {rank_range: count}
    class Meta:
        managed = False
        db_table = 'statistics_exam_indicators'
        unique_together = (('exam', 'subject', 'select_type', 'level_type'),)


# StatisticsPrecomputedMetrics模型的简化版本
class StatisticsPrecomputedMetrics(models.Model):
    """预计算统计指标表"""
    metric_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey('score_processor.BaseExamConfig', models.DO_NOTHING, db_comment='考试ID')
    subject = models.ForeignKey('score_processor.BaseSubjectConfig', models.DO_NOTHING, null=True,
                                db_comment='科目(为空表示总分)')
    select_type = models.CharField(max_length=10, db_comment='文科/理科')
    level_type = models.CharField(max_length=20, db_comment='分析层级：city/district/school')
    metric_type = models.CharField(max_length=50, db_comment='指标类型')

    # 统计值
    metric_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, db_comment='指标值')
    auxiliary_data = models.JSONField(null=True, db_comment='辅助数据')  # 存储计算过程数据或补充信息

    # 计算控制
    last_computed = models.DateTimeField(db_comment='最后计算时间')
    compute_duration = models.IntegerField(null=True, db_comment='计算耗时(秒)')

    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'statistics_precomputed_metrics'
        unique_together = (('exam', 'subject', 'select_type', 'level_type', 'metric_type'),)


class ScoreRankings(models.Model):
    ranking_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey(BaseExamConfig, models.DO_NOTHING, db_comment='考试ID')
    unified_student_id = models.CharField(max_length=50, db_comment='统一学生ID')
    student_name = models.CharField(max_length=50)    # 新增
    school_name = models.CharField(max_length=100)    # 新增
    subject = models.ForeignKey(BaseSubjectConfig, models.DO_NOTHING, db_comment='科目ID')
    select_type = models.CharField(max_length=10, db_comment='文科/理科')
    level_type = models.CharField(max_length=20, db_comment='分析层级：city/district/school')
    raw_score = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    raw_score_rank = models.IntegerField(null=True)
    total_count = models.IntegerField(null=True, db_comment='总人数')
    percentile = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    create_time = models.DateTimeField(auto_now_add=True)
    class Meta:
        managed = False
        db_table = 'score_rankings'
        verbose_name = '排名情况统计'
        verbose_name_plural = '排名情况统计'
        unique_together = (('exam', 'unified_student_id', 'subject', 'select_type', 'level_type'),)