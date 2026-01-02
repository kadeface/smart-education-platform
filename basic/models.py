# basic/models.py
from django.db import models
from django.utils import timezone


class StudentIDMapping(models.Model):
    """学生ID映射表 - 处理学生在不同学段的ID对应关系"""
    SCHOOL_LEVEL_CHOICES = [
        ('H', '高中'),
        ('M', '初中'),
        ('P', '小学')
    ]

    student_name = models.CharField('学生姓名', max_length=50)
    student_registration = models.CharField('学籍号', max_length=20, unique=True, help_text='全国统一学籍号')
    id_number = models.CharField('身份证号', max_length=18, unique=True)

    # 各学段学号
    primary_id = models.CharField('小学学号', max_length=50, null=True, blank=True)
    middle_id = models.CharField('初中学号', max_length=50, null=True, blank=True)
    high_id = models.CharField('高中学号', max_length=50, null=True, blank=True)
    current_level = models.CharField('当前学段', max_length=1, choices=SCHOOL_LEVEL_CHOICES)

    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'student_id_mapping'
        verbose_name = '学生ID映射'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['student_registration']),
            models.Index(fields=['id_number']),
            models.Index(fields=['primary_id']),
            models.Index(fields=['middle_id']),
            models.Index(fields=['high_id']),
            models.Index(fields=['student_name']),
        ]
