from django.db import models
from .base import BaseExamConfig, BaseSubjectConfig


class LayerAnalysis(models.Model):
    """总分层次基础分析"""
    layer_id = models.AutoField(primary_key=True)
    exam_id = models.CharField(max_length=50, help_text='考试ID')
    select_type = models.CharField(max_length=10, choices=[('文科', '文科'), ('理科', '理科')])
    layer_type = models.CharField(max_length=20, help_text='层次类型：如top10/top50等')

    # 基础统计（保留这些字段用于快速查询）
    student_count = models.IntegerField(help_text='该层次学生总数')
    mean_score = models.DecimalField(max_digits=10, decimal_places=2, help_text='平均分')
    max_score = models.DecimalField(max_digits=10, decimal_places=2, help_text='最高分')
    min_score = models.DecimalField(max_digits=10, decimal_places=2, help_text='最低分')
    std_dev = models.DecimalField(max_digits=10, decimal_places=2, help_text='标准差')

    # 新增JSON字段存储详细统计数据
    stats_data = models.JSONField('统计数据', default=dict, help_text='包含学校分布等详细统计数据')

    # 时间字段
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'layer_analysis'
        unique_together = ['exam_id', 'select_type', 'layer_type']
        verbose_name = '总分层次分析'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.exam_id}-{self.select_type}-{self.layer_type}"


class RegionLayerDetail(models.Model):
    """区域层次详细分析（区县和学校）"""
    detail_id = models.AutoField(primary_key=True)
    layer = models.ForeignKey('LayerAnalysis', on_delete=models.CASCADE)
    district_name = models.CharField(max_length=50, help_text='区县名称')
    school_name = models.CharField(max_length=100, null=True, help_text='学校名称，区县汇总时为空')

    # 人数统计
    student_count = models.IntegerField(help_text='该区域在该层次的学生数')
    total_student_count = models.IntegerField(help_text='该区域的总学生数')
    layer_ratio = models.DecimalField(max_digits=5, decimal_places=2, help_text='占该层次总人数比例')
    region_ratio = models.DecimalField(max_digits=5, decimal_places=2, help_text='占本区域总人数比例')

    # 分数统计
    mean_score = models.DecimalField(max_digits=10, decimal_places=2, help_text='平均分')
    max_score = models.DecimalField(max_digits=10, decimal_places=2, help_text='最高分')
    min_score = models.DecimalField(max_digits=10, decimal_places=2, help_text='最低分')
    std_dev = models.DecimalField(max_digits=10, decimal_places=2, help_text='标准差')

    # 差距分析
    city_diff = models.DecimalField(max_digits=10, decimal_places=2, help_text='与市平均分差距')
    district_diff = models.DecimalField(max_digits=10, decimal_places=2, null=True,
                                        help_text='与区县平均分差距(学校使用)')

    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'region_layer_detail'
        unique_together = ['layer', 'district_name', 'school_name']
        indexes = [
            models.Index(fields=['district_name']),
            models.Index(fields=['school_name']),
        ]

class RegionCharacteristics(models.Model):
    """区域特征分析"""
    characteristics_id = models.AutoField(primary_key=True)
    exam_id = models.CharField(max_length=50, help_text='考试ID')
    district_name = models.CharField(max_length=50, help_text='区县名称')
    select_type = models.CharField(
        max_length=10,
        choices=[('文科', '文科'), ('理科', '理科')],
        help_text='文理分科'
    )
    layer_type = models.CharField(
        max_length=20,
        default='all',
        help_text='层次类型'
    )

    # 学科特征
    subject_features = models.JSONField(help_text="""
    {
        "strong_subjects": [
            {
                "subject": "语文",
                "t_score": 58.5,
                "rank": 1,
                "mean": 85.5,
                "excellent_rate": 25.5,
                "pass_rate": 85.2,
                "distribution": {
                    "excellent": 150,
                    "good": 350,
                    "fail": 100
                },
                "distribution_rate": {
                    "excellent": 25.5,
                    "good": 58.3,
                    "fail": 16.2
                }
            },
            ...
        ],
        "weak_subjects": [...],
        "all_subjects": [...],
        "score_lines": {
            "excellent_line": 650,
            "pass_line": 500
        }
    }
    """)

    # 分布特征
    distribution_features = models.JSONField(help_text="""
    {
        "distribution_type": "正态分布",
        "key_indicators": {
            "mean": 85.5,
            "std_dev": 12.3,
            "max_score": 98,
            "min_score": 45,
            "median": 86
        }
    }
    """)

    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'region_characteristics'
        unique_together = ['exam_id', 'district_name', 'select_type', 'layer_type']
        verbose_name = '区域特征分析'
        verbose_name_plural = '区域特征分析'
        indexes = [
            models.Index(fields=['exam_id']),
            models.Index(fields=['district_name']),
            models.Index(fields=['layer_type']),
        ]

    def __str__(self):
        return f"{self.district_name}-{self.exam_id}-{self.layer_type}"


class RegionProgress(models.Model):
    """区域进步分析"""
    progress_id = models.AutoField(primary_key=True)
    exam_id = models.CharField(max_length=50, help_text='当前考试ID')
    district_name = models.CharField(max_length=50, help_text='区县名称')
    select_type = models.CharField(
        max_length=10,
        choices=[('文科', '文科'), ('理科', '理科')],
        help_text='文理分科'
    )

    # 进步分析数据
    progress_data = models.JSONField(help_text="""
    {
        "progress_data": {
            "语文": {
                "t_score_change": 1.2,
                "mean_change": 2.5,
                "excellent_rate_change": 1.5,
                "pass_rate_change": 0.8,
                "current": {...},
                "previous": {...}
            },
            ...
        },
        "strong_subjects_change": {
            "maintained": ["语文", "数学"],
            "new": ["英语"],
            "lost": ["物理"]
        },
        "weak_subjects_change": {
            "maintained": ["化学"],
            "new": ["物理"],
            "improved": ["生物"]
        },
        "summary": {
            "most_improved": [...],
            "most_declined": [...],
            "overall_trend": "up",
            "strength_changes": {
                "improved": 1,
                "weakened": 1
            },
            "highlights": {...},
            "concerns": {...}
        }
    }
    """)

    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'region_progress'
        unique_together = ['exam_id', 'district_name', 'select_type']
        verbose_name = '区域进步分析'
        verbose_name_plural = '区域进步分析'
        indexes = [
            models.Index(fields=['exam_id']),
            models.Index(fields=['district_name']),
            models.Index(fields=['select_type']),
        ]

    def __str__(self):
        return f"{self.district_name}-{self.exam_id}"