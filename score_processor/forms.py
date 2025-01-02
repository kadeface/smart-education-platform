from django import forms
#from .models import ExamUpload
from score_processor.models import BaseExamConfig
class ScoreUploadForm(forms.Form):
    base_subject_config = forms.ModelChoiceField(
        label='考试配置',
        queryset=BaseExamConfig.objects.all().order_by('-exam_date','exam_name'),
        required=True,
        empty_label="请选择考试"
    )
    file = forms.FileField(label='成绩文件')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 自定义考试配置的显示方式
        self.fields['base_subject_config'].label_from_instance = \
            lambda obj: f"{obj.exam_name} ({obj.exam_date})"

