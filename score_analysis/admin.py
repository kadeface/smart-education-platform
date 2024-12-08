#score_analysis/admin.py:
from django.contrib import admin
from django import forms
from .models.statistics import ExamScoreLines
from .models.base import BaseExamConfig
from django.core.exceptions import ValidationError

class ExamScoreLinesForm(forms.ModelForm):
    # 自定义表单字段
    exam_id = forms.ChoiceField(label='考试ID')

    class Meta:
        model = ExamScoreLines
        fields = ['exam_id', 'stream_type', 'line_type', 'score']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 动态获取考试列表
        exams = BaseExamConfig.objects.all().values_list('exam_id', 'exam_name')
        self.fields['exam_id'].choices = [(exam[0], f"{exam[0]} - {exam[1]}") for exam in exams]
# 如果是编辑现有记录，设置初始选中值
        instance = kwargs.get('instance')
        if instance:
            # 设置exam_id的初始值
            self.initial['exam_id'] = instance.exam_id
            # stream_type和line_type会自动设置，因为它们是model字段
@admin.register(ExamScoreLines)
class ExamScoreLinesAdmin(admin.ModelAdmin):
    list_display = ['exam_id', 'stream_type', 'line_type', 'score', 'create_time', 'update_time']
    list_filter = ['stream_type', 'line_type']
    search_fields = ['exam_id']
    readonly_fields = ['create_time', 'update_time']  # 修改为实际存在的字段

    fieldsets = (
        ('基本信息', {
            'fields': ('exam_id', 'stream_type', 'line_type', 'score')
        }),
        ('时间信息', {
            'fields': ('create_time', 'update_time'),
            'classes': ('collapse',)
        })
    )

