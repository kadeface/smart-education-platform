# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models

class BaseExamConfig(models.Model):
    exam_id = models.CharField(primary_key=True, max_length=50, db_comment='考试ID')
    exam_name = models.CharField(max_length=100, db_comment='考试名称')
    exam_date = models.DateField(db_comment='考试日期')
    exam_type = models.CharField(max_length=20, blank=True, null=True, db_comment='考试类型：月考/期中/模拟等')
    grade_level = models.CharField(max_length=20, blank=True, null=True, db_comment='年级')
    semester = models.CharField(max_length=20, blank=True, null=True, db_comment='学期')
    status = models.CharField(max_length=10, blank=True, null=True, db_comment='状态：active/inactive')
    create_time = models.DateTimeField(blank=True, null=True)
    update_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        app_label = 'score_processor'
        managed = False
        db_table = 'base_exam_config'
        db_table_comment = '考试基本信息表'
        verbose_name = '考试基础信息设置'
        verbose_name_plural = verbose_name

class BaseSchoolInfo(models.Model):
    school_id = models.AutoField(primary_key=True)
    district_id = models.IntegerField(blank=True, null=True)
    school_code = models.CharField(max_length=20, blank=True, null=True)
    school_name = models.CharField(max_length=100, blank=True, null=True)
    school_type = models.CharField(max_length=20, blank=True, null=True)
    school_level = models.CharField(max_length=20, blank=True, null=True)
    create_time = models.DateTimeField(blank=True, null=True)
    update_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'base_school_info'

class BaseSubjectConfig(models.Model):
    subject_id = models.CharField(primary_key=True, max_length=20, db_comment='科目ID')
    subject_name = models.CharField(max_length=50, db_comment='科目名称')
    subject_type = models.CharField(max_length=20, blank=True, null=True, db_comment='科目类型：主科/副科')
    full_score = models.IntegerField(db_comment='满分')
    is_required = models.IntegerField(blank=True, null=True, db_comment='是否必修')
    create_time = models.DateTimeField(blank=True, null=True)
    update_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'base_subject_config'
        db_table_comment = '科目配置表'

class ScoreStudentBasic(models.Model):
    exam_id = models.CharField(max_length=50)
    student_id = models.CharField(max_length=50)
    student_name = models.CharField(max_length=50)
    district_name = models.CharField(max_length=50)
    school_name = models.CharField(max_length=100)
    class_field = models.CharField(db_column='class', max_length=50)  # Field renamed because it was a Python reserved word.
    select_type = models.CharField(max_length=10, db_comment='文科/理科/未确定')
    chinese = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    math = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    english = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    physics = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    chemistry = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    biology = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    history = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    politics = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    geography = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    total_score = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    create_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'score_student_basic'
        db_table_comment = '学生基础成绩表'
        verbose_name = '学生基础成绩表'
        verbose_name_plural = verbose_name

class StudentMapping(models.Model):
    unified_id = models.CharField(max_length=11, db_comment='统一考号(11位)')
    exam_id = models.CharField(max_length=50, db_comment='考试ID')
    original_student_id = models.CharField(max_length=50, db_comment='原始考号')
    student_name = models.CharField(max_length=50, db_comment='学生姓名')
    school_name = models.CharField(max_length=100, db_comment='学校名称')
    class_name = models.CharField(max_length=50, db_comment='班级名称')
    create_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'student_mapping'
        unique_together = (('exam_id', 'original_student_id'),)
        verbose_name = '学号映射表'
        verbose_name_plural = verbose_name


class ExamUpload(models.Model):
    SCHOOL_LEVEL_CHOICES = [
        ('H', '高中'),
        ('M', '初中'),
        ('P', '小学'),
    ]

    STATUS_CHOICES = [
        ('PENDING', '待处理'),
        ('PROCESSING', '处理中'),
        ('COMPLETED', '已完成'),
        ('FAILED', '失败'),
    ]

    exam_id = models.CharField('考试ID', max_length=20)
    file = models.FileField('文件', upload_to='uploads/')
    uploaded_at = models.DateTimeField('上传时间', auto_now_add=True)
    status = models.CharField('状态', max_length=10, choices=STATUS_CHOICES, default='PENDING')
    error_message = models.TextField('错误信息', blank=True, null=True)
    school_level = models.CharField('学段', max_length=1, choices=SCHOOL_LEVEL_CHOICES, default='H')
    base_subject_config = models.ForeignKey(
        'BaseExamConfig',
        to_field='exam_id',  # 指定关联到 exam_id 字段
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='考试配置',
        db_column='base_subject_config_id'
    )
    class Meta:
        verbose_name = '成绩上传'
        verbose_name_plural = '成绩上传'
        managed = False
        db_table = 'exam_uploads'

    def __str__(self):
        return f"{self.exam_id} ({self.get_status_display()})"

class ExamSubjectConfig(models.Model):
    """考试科目配置表"""
    config_id = models.BigAutoField(primary_key=True)
    exam = models.ForeignKey('BaseExamConfig', models.DO_NOTHING, db_comment='考试ID')
    subject = models.ForeignKey('BaseSubjectConfig', models.DO_NOTHING, db_comment='科目ID')

    # 分数线设置
    full_score = models.DecimalField(max_digits=5, decimal_places=2, db_comment='满分')
    pass_score = models.DecimalField(max_digits=5, decimal_places=2, db_comment='及格分数线')
    excellent_score = models.DecimalField(max_digits=5, decimal_places=2, db_comment='优秀分数线')

    # 权重设置
    weight = models.DecimalField(max_digits=3, decimal_places=2, default=1.00, db_comment='分数权重')

    # 统计指标
    mean_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='平均分')
    std_dev = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='标准差')
    max_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='最高分')
    min_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='最低分')

    # 达标率
    pass_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='及格率')
    excellent_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='优秀率')
    low_score_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, db_comment='低分率')

    # 配置状态
    status = models.CharField(max_length=10, default='active', db_comment='状态：active/inactive')
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'exam_subject_config'
        unique_together = (('exam', 'subject'),)
        indexes = [
            models.Index(fields=['exam', 'subject']),
            models.Index(fields=['subject', 'status']),
        ]
        verbose_name = '考试科目配置'
        verbose_name_plural = verbose_name