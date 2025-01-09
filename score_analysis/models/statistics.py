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
        verbose_name = '基础指标统计'
        verbose_name_plural = '基础指标统计'

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


class ExamLevelStatistics(models.Model):
    """考试分层统计数据"""
    LEVEL_CHOICES = [
        ('city', '市级'),
        ('district', '区县'),
        ('school', '学校')
    ]

    indicator_id = models.AutoField(primary_key=True)
    exam_id = models.CharField('考试ID', max_length=50)
    select_type = models.CharField(
        '分科类型',
        max_length=10,
        choices=[('文科', '文科'), ('理科', '理科'), ('未分科', '未分科')]
    )
    level_type = models.CharField(
        '统计层级',
        max_length=10,
        choices=LEVEL_CHOICES
    )
    district_name = models.CharField('区县名称', max_length=50, null=True, blank=True)
    # 基础统计指标
    student_count = models.IntegerField('考生人数')
    max_score = models.DecimalField('最高分', max_digits=5, decimal_places=2)
    min_score = models.DecimalField('最低分', max_digits=5, decimal_places=2)
    mean_score = models.DecimalField('平均分', max_digits=5, decimal_places=2)
    median_score = models.DecimalField('中位数', max_digits=5, decimal_places=2)
    std_dev = models.DecimalField('标准差', max_digits=5, decimal_places=2)

    # 分位数统计
    q80_score = models.DecimalField('80分位数', max_digits=5, decimal_places=2)
    q20_score = models.DecimalField('20分位数', max_digits=5, decimal_places=2)
    q10_score = models.DecimalField('10分位数', max_digits=5, decimal_places=2)

    # 达标率统计
    excellent_rate = models.DecimalField('优秀率', max_digits=5, decimal_places=2)
    pass_rate = models.DecimalField('及格率', max_digits=5, decimal_places=2)
    low_score_rate = models.DecimalField('低分率', max_digits=5, decimal_places=2)

    # JSON字段存储详细分布
    rank_distribution = models.JSONField('排名分布', default=dict)
    school_distribution = models.JSONField('学校分布', default=dict)
    threshold_stats = models.JSONField('分数线统计', default=dict)

    create_time = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'exam_level_statistics'
        unique_together = ['exam_id', 'select_type', 'level_type']
        verbose_name = '考试分层统计'
        verbose_name_plural = verbose_name

    def __str__(self):
        level_names = dict(self.LEVEL_CHOICES)
        return f"{self.exam_id}-{level_names[self.level_type]}-{self.select_type}"

    def save_ranking_stats(self, ranking_stats: dict):
        """保存排名统计数据"""
        self.student_count = ranking_stats['total_students']
        self.max_score = ranking_stats['max_score']
        self.min_score = ranking_stats['min_score']
        self.mean_score = ranking_stats['mean_score']

        # 保存分位数
        self.q80_score = ranking_stats.get(f'top_{int(self.student_count * 0.2)}_score', 0)
        self.q20_score = ranking_stats.get(f'top_{int(self.student_count * 0.8)}_score', 0)
        self.q10_score = ranking_stats.get(f'top_{int(self.student_count * 0.9)}_score', 0)

        # 计算中位数
        median_rank = int(self.student_count * 0.5)
        self.median_score = ranking_stats.get(f'top_{median_rank}_score', 0)

        # 计算标准差 (使用80分位和20分位的差值除以2.5作为估计)
        self.std_dev = (self.q80_score - self.q20_score) / 2.5

        # 保存排名分布
        self.rank_distribution = {
            f'top_{rank}': {
                'score': ranking_stats.get(f'top_{rank}_score'),
                't_score': ranking_stats.get(f'top_{rank}_t_score'),
                'percentile': ranking_stats.get(f'top_{rank}_percentile')
            }
            for rank in [10, 50, 100, 200, 1250, 3000, 9600]
            if ranking_stats.get(f'top_{rank}_score')
        }

        # 保存阈值统计
        self.threshold_stats = {
            'excellent': {
                'score': self.q80_score,
                'rate': 20.0
            },
            'pass': {
                'score': self.q20_score,
                'rate': 80.0
            },
            'low': {
                'score': self.q10_score,
                'rate': 90.0
            }
        }

        # 计算达标率
        self.excellent_rate = 20.0  # 默认取前20%
        self.pass_rate = 80.0  # 默认取前80%
        self.low_score_rate = 10.0  # 默认取后10%

        self.save()


class ExamLevelAnalysisConfig(models.Model):
    """考试分层分析配置

    此配置用于设置考试分层分析的参数，包括：
    1. 排名分析配置：设置需要统计的排名范围（如TOP10、TOP50等）
    2. 分数线配置：设置各类分数线的划分比例

    主要用途：
    1. 为不同类型的考试提供不同的分析配置
    2. 支持多套配置方案的切换和复用
    3. 确保分析参数的一致性和可追溯性

    使用场景：
    1. 期中/期末考试可能需要不同的排名范围
    2. 不同区域可能需要不同的分数线划分
    3. 临时性的专项分析可能需要特殊配置
    4. 文理分科考试需要不同的配置
    """

    # 分科类型选项
    SELECT_TYPE_CHOICES = [
        ('文科', '文科'),
        ('理科', '理科'),
        ('未分科', '未分科')
    ]

    # 预设的排名范围选项
    RANK_RANGES = [
        (10, 'TOP10'),
        (20, 'TOP20'),
        (50, 'TOP50'),
        (100, 'TOP100'),
        (200, 'TOP200'),
        (500, 'TOP500'),
    ]

    # 预设的分数线类型
    SCORE_LINE_TYPES = [
        ('C9', 'C9高校'),
        ('985', '985高校'),
        ('211', '211高校'),
        ('特控', '特控线'),
        ('本科', '本科线'),
        ('专科', '专科线'),
    ]

    # 三率分数线类型（未分科使用）
    THREE_RATE_TYPES = [
        ('优秀', '优秀线'),
        ('合格', '合格线'),
        ('低分', '低分线'),
    ]

    config_id = models.AutoField(primary_key=True)
    exam_id = models.CharField('考试ID', max_length=50)
    select_type = models.CharField(
        '分科类型',
        max_length=20,
        choices=SELECT_TYPE_CHOICES,
        default='未分科',
        help_text='选择考试的分科类型'
    )
    name = models.CharField('配置名称', max_length=50)
    is_active = models.BooleanField('是否启用', default=True)

    rank_ranges = models.JSONField(
        '排名配置',
        default=dict,
        help_text='''
        按区域配置排名范围，格式如：
        {
            "市级": [10, 20, 50, 100, 200, 500],
            "开平市": [10, 50, 300, 600],
            "恩平市": [10, 50, 200],
            "default": [10, 50, 100]  # 默认配置
        }
        '''
    )

    score_lines = models.JSONField(
        '分数线配置',
        default=dict,
        help_text='''
        分数线配置，格式如：
        # 文理分科考试：
        {
            "C9": 680,
            "985": 650,
            "211": 620,
            "特控": 600,
            "本科": 550,
            "专科": 450
        }
        # 未分科考试：
        {
            "优秀": 85,
            "合格": 60,
            "低分": 36
        }
        '''
    )

    description = models.TextField('说明', blank=True)
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'exam_level_analysis_config'
        verbose_name = '考试分层分析配置'
        verbose_name_plural = verbose_name
        unique_together = ['exam_id', 'select_type', 'name']

    def __str__(self):
        return f"{self.name}({self.select_type})({'启用' if self.is_active else '禁用'})"

    def get_score_lines_display(self):
        """获取分数线配置的显示文本"""
        display = []
        for line_type, score in self.score_lines.items():
            if self.select_type == '未分科':
                display.append(f"{line_type}({score}分)")
            else:
                display.append(f"{line_type}({score}分)")
        return ', '.join(display)
    get_score_lines_display.short_description = '分数线配置'

    def get_rank_ranges_display(self, district=None):
        """获取排名范围的显示文本"""
        area = district or '市级'
        ranges = self.rank_ranges.get(area) or self.rank_ranges.get('default', [])
        return f"TOP{', TOP'.join(map(str, ranges))}"
    get_rank_ranges_display.short_description = '排名配置'

    def get_district_list(self):
        """获取配置的区域列表"""
        districts = set(self.rank_ranges.keys())
        districts.discard('default')
        districts.discard('市级')
        return sorted(districts)
    get_district_list.short_description = '配置区域'

    def get_line_types(self):
        """获取分数线类型列表"""
        if self.select_type == '未分科':
            return self.THREE_RATE_TYPES
        return self.SCORE_LINE_TYPES

    def __str__(self):
        return f"{self.name}({self.select_type})({'启用' if self.is_active else '禁用'})"

    def get_score_line_display(self):
        """获取分数线配置的显示文本"""
        lines = []
        for line in self.score_lines:
            lines.append(f"{line['type']}({line['ratio'] * 100:.1f}%)")
        return ', '.join(lines)

    get_score_line_display.short_description = '分数线配置'

    def get_rank_ranges_display(self):
        """获取排名范围的显示文本"""
        return f"TOP{', TOP'.join(map(str, self.rank_ranges))}"

    get_rank_ranges_display.short_description = '排名配置'


class ExamLevelAnalysisTask(models.Model):
    """考试分层分析任务

    用于管理和追踪考试分层分析的执行过程，包括：
    1. 记录分析任务的执行状态
    2. 关联具体的分析配置
    3. 保存错误信息（如果有）

    分析内容：
    1. 市级整体情况分析
    2. 区县层面横向对比
    3. 学校层面横向对比
    4. 排名分布统计
    5. 分数线达线情况

    任务状态流转：
    pending(待执行) -> running(执行中) -> completed(已完成)/failed(失败)
    """

    STATUS_CHOICES = [
        ('pending', '待执行'),
        ('running', '执行中'),
        ('completed', '已完成'),
        ('failed', '失败')
    ]

    task_id = models.AutoField(primary_key=True)
    exam_id = models.CharField(
        '考试ID',
        max_length=50,
        help_text='要分析的考试ID，格式如：202411-DIST-H-2025'
    )
    config = models.ForeignKey(
        ExamLevelAnalysisConfig,
        on_delete=models.PROTECT,
        verbose_name='分析配置',
        help_text='使用的分析配置方案'
    )
    status = models.CharField(
        '状态',
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text='任务执行状态'
    )
    error_message = models.TextField(
        '错误信息',
        blank=True,
        help_text='任务执行失败时的错误信息'
    )
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'exam_level_analysis_task'
        verbose_name = '考试分层分析任务'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"考试{self.exam_id}的分析任务(状态:{self.get_status_display()})"