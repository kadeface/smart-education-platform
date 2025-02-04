from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

from score_analysis.models import ScoreStudentBasic


class TrackingGroup(models.Model):
    """跟踪分组"""
    SCHOOL_LEVEL_CHOICES = [
        ('H', '高中'),
        ('M', '初中'),
        ('P', '小学'),
    ]
    STUDENT_TYPE_CHOICES = [
        ('SCIENCE', '理科'),
        ('LIBERAL', '文科'),
        ('UNKNOWN', '未分科'),  # 包含未分科和不分文理的情况
    ]

    student_type = models.CharField(
        '学生类型',
        max_length=10,
        choices=STUDENT_TYPE_CHOICES,
        default='UNKNOWN'
    )
    group_name = models.CharField('分组名称', max_length=50)
    school_level = models.CharField('学段', max_length=1, choices=SCHOOL_LEVEL_CHOICES)
    grade_level = models.CharField('年级', max_length=10)
    layer_type = models.CharField('分层类型', max_length=20)
    score_range = models.CharField('分数线范围', max_length=20, null=True, blank=True)
    description = models.TextField('描述', null=True, blank=True)
    create_time = models.DateTimeField('创建时间', default=timezone.now)
    update_time = models.DateTimeField('更新时间', auto_now=True)
    status = models.BooleanField('启用状态', default=True)

    def __str__(self):
        return f"{self.group_name} ({self.get_school_level_display()})"

    class Meta:
        db_table = 'tracking_groups'
        verbose_name = '跟踪分组'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['grade_level', 'school_level']),
            models.Index(fields=['student_type']),
        ]


class TrackingStudent(models.Model):
    """跟踪学生"""
    group = models.ForeignKey(TrackingGroup, on_delete=models.CASCADE, verbose_name='所属分组')
    student_id = models.CharField('学生ID', max_length=50, db_index=True)
    student_name = models.CharField('学生姓名', max_length=50)
    class_name = models.CharField('班级名称', max_length=50)
    entry_score = models.DecimalField('入组成绩', max_digits=5, decimal_places=2, null=True)
    entry_rank = models.IntegerField('入组排名', null=True)
    entry_exam = models.ForeignKey('TrackingExam', on_delete=models.SET_NULL, null=True, verbose_name='入组考试')
    entry_time = models.DateTimeField('入组时间', default=timezone.now)
    exit_time = models.DateTimeField('退出时间', null=True, blank=True)
    status = models.BooleanField('跟踪状态', default=True)

    def __str__(self):
        return f"{self.student_name} ({self.student_id})"

    class Meta:
        db_table = 'tracking_students'
        verbose_name = '跟踪学生'
        verbose_name_plural = verbose_name


class TrackingExam(models.Model):
    """跟踪考试"""
    EXAM_LEVEL_CHOICES = [
        ('CITY', '市级考试'),
        ('DIST', '区县级考试'),
        ('SCHOOL', '校级考试'),
    ]

    EXAM_WEIGHT_CHOICES = [
        (1.0, '标准权重'),
        (1.2, '市级权重'),
        (0.8, '校级权重'),
    ]

    exam_id = models.CharField('考试ID', max_length=50, unique=True)
    group = models.ForeignKey(TrackingGroup, on_delete=models.CASCADE, verbose_name='关联分组')
    exam_date = models.DateField('考试日期')
    exam_level = models.CharField('考试层级', max_length=10, choices=EXAM_LEVEL_CHOICES)
    exam_weight = models.FloatField('考试权重', choices=EXAM_WEIGHT_CHOICES, default=1.0)
    reference_group = models.CharField('参考群体', max_length=20)
    status = models.BooleanField('跟踪状态', default=True)

    def __str__(self):
        return f"{self.exam_id} ({self.get_exam_level_display()})"

    class Meta:
        db_table = 'tracking_exams'
        verbose_name = '跟踪考试'
        verbose_name_plural = verbose_name


class BaseExamRecord(models.Model):
    """考试记录基类"""
    student_id = models.CharField('学生ID', max_length=50)
    exam_id = models.CharField('考试ID', max_length=50)
    total_score = models.DecimalField('原始总分', max_digits=5, decimal_places=2)
    total_t_score = models.DecimalField('总分T分', max_digits=5, decimal_places=2)

    city_rank = models.IntegerField('市级排名', null=True)
    district_rank = models.IntegerField('区县排名', null=True)
    school_rank = models.IntegerField('校级排名', null=True)

    city_t_score = models.DecimalField('市级T分', max_digits=5, decimal_places=2, null=True)
    district_t_score = models.DecimalField('区级T分', max_digits=5, decimal_places=2, null=True)
    school_t_score = models.DecimalField('校级T分', max_digits=5, decimal_places=2, null=True)

    subject_scores = models.JSONField('各科原始分', null=True)
    subject_t_scores = models.JSONField('各科T分', null=True)
    subject_ranks = models.JSONField('各科排名', null=True)

    class Meta:
        abstract = True


class TrackingRecord(BaseExamRecord):
    """跟踪记录"""
    weighted_t_score = models.DecimalField('加权T分', max_digits=5, decimal_places=2)
    improvement = models.DecimalField('进步分数', max_digits=5, decimal_places=2, null=True)
    t_improvement = models.DecimalField('T分进步', max_digits=5, decimal_places=2, null=True)
    weighted_improvement = models.DecimalField('加权进步', max_digits=5, decimal_places=2, null=True)
    percentile = models.DecimalField('超越率', max_digits=5, decimal_places=2, null=True)
    create_time = models.DateTimeField('创建时间', default=timezone.now)
    select_type = models.CharField(max_length=20, null=True, blank=True)
    class Meta:
        db_table = 'tracking_records'
        verbose_name = '发展跟踪模块'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['student_id', 'exam_id']),
        ]


class TrackingAnalysis(models.Model):
    """跟踪分析"""
    student = models.ForeignKey(TrackingStudent, on_delete=models.CASCADE, verbose_name='学生')
    exam = models.ForeignKey(TrackingExam, on_delete=models.CASCADE, verbose_name='考试')
    stability_score = models.DecimalField('稳定性得分', max_digits=5, decimal_places=2, null=True)
    trend_direction = models.SmallIntegerField('趋势', null=True)
    subject_strength = models.JSONField('学科优势', null=True)
    improvement_rate = models.DecimalField('进步率', max_digits=5, decimal_places=2, null=True)
    analysis_time = models.DateTimeField('分析时间', default=timezone.now)

    class Meta:
        db_table = 'tracking_analysis'
        verbose_name = '跟踪分析'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['student', 'exam']),
        ]


class TrackingTarget(models.Model):
    """跟踪目标"""
    student = models.ForeignKey(TrackingStudent, on_delete=models.CASCADE, verbose_name='学生')
    target_type = models.CharField('目标类型', max_length=20)
    target_value = models.DecimalField('目标值', max_digits=5, decimal_places=2)
    start_exam = models.ForeignKey(TrackingExam, on_delete=models.CASCADE, related_name='target_start_exams')
    end_exam = models.ForeignKey(TrackingExam, on_delete=models.SET_NULL, null=True, related_name='target_end_exams')
    achievement_rate = models.DecimalField('达成率', max_digits=5, decimal_places=2, null=True)
    status = models.BooleanField('达成状态', default=False)
    create_time = models.DateTimeField('创建时间', default=timezone.now)

    class Meta:
        db_table = 'tracking_targets'
        verbose_name = '跟踪目标'
        verbose_name_plural = verbose_name


class TaggedStudent(models.Model):
    """标签学生群模型"""

    # 标签类型选项
    TAG_TYPES = [
        ('elite', '尖子生'),
        ('potential_elite', '潜力尖子'),
        ('potential_special', '潜力特控'),
        ('potential_regular', '潜力本科')
    ]

    # 文理分科选项
    SUBJECT_TYPES = [
        ('理科', '理科'),
        ('文科', '文科')
    ]

    # 数据库字段
    id = models.BigAutoField(primary_key=True)
    tag_type = models.CharField(
        max_length=20,
        choices=TAG_TYPES,
        verbose_name='标签类型',
        help_text='标签类型:尖子生/潜力尖子/潜力特控/潜力本科'
    )
    subject_type = models.CharField(
        max_length=10,
        choices=SUBJECT_TYPES,
        verbose_name='文理分科',
        help_text='文理分科:理科/文科'
    )
    features = models.JSONField(
        null=True,
        verbose_name='特征数据',
        help_text="""
        {
            'advantages': ['数学', '物理'],  # 优势学科
            'potential_points': ['逻辑思维', '学习态度'],  # 潜力特征点
            'growth_rate': 0.15,  # 成长率
            'stability': 0.85,  # 稳定性
            'competition_awards': ['数学竞赛省一等奖'],  # 竞赛获奖
            'special_talents': ['科技创新']  # 特殊才能
        }
        """
    )
    remarks = models.TextField(
        null=True,
        verbose_name='备注'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='是否有效'
    )
    marked_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='标记时间'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间'
    )
    exam_id = models.CharField(
        max_length=32,
        verbose_name='考试ID'
    )
    school_name = models.CharField(
        max_length=32,
        verbose_name='学校名称'
    )
    student_id = models.CharField(
        max_length=32,
        verbose_name='学生ID'
    )

    class Meta:
        db_table = 'tagged_student'
        verbose_name = '标签学生'
        verbose_name_plural = '标签学生'
        unique_together = ['student_id', 'exam_id', 'tag_type']
        indexes = [
            models.Index(fields=['student_id', 'exam_id'], name='idx_student_exam'),
        ]

    def __str__(self):
        return f"{self.student_id}-{self.get_tag_type_display()}"

    def get_student_info(self):
        """获取学生基本信息"""
        return ScoreStudentBasic.objects.filter(
            student_id=self.student_id,
            exam_id=self.exam_id
        ).first()

    @property
    def score_info(self):
        """获取成绩信息"""
        student = self.get_student_info()
        if student:
            return {
                'student_name': student.student_name,
                'total_score': student.total_score,
                'rank': student.rank,
                'subject_scores': {
                    '语文': student.chinese_score,
                    '数学': student.math_score,
                    '英语': student.english_score,
                    # 根据文理科添加其他科目
                    **self._get_optional_subjects(student)
                },
                't_scores': {
                    '语文': student.chinese_t_score,
                    '数学': student.math_t_score,
                    '英语': student.english_t_score,
                    # 根据文理科添加其他科目T分
                    **self._get_optional_t_scores(student)
                }
            }
        return None

    def _get_optional_subjects(self, student):
        """获取选考科目成绩"""
        if self.subject_type == '理科':
            return {
                '物理': student.physics_score,
                '化学': student.chemistry_score,
                '生物': student.biology_score
            }
        else:
            return {
                '政治': student.politics_score,
                '历史': student.history_score,
                '地理': student.geography_score
            }

    def _get_optional_t_scores(self, student):
        """获取选考科目T分"""
        if self.subject_type == '理科':
            return {
                '物理': student.physics_t_score,
                '化学': student.chemistry_t_score,
                '生物': student.biology_t_score
            }
        else:
            return {
                '政治': student.politics_t_score,
                '历史': student.history_t_score,
                '地理': student.geography_t_score
            }