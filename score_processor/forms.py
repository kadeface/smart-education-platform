from django import forms
#from .models import ExamUpload
from score_processor.models import BaseExamConfig
class ScoreUploadForm(forms.Form):
    file = forms.FileField(label='成绩文件')
    exam_id = forms.ChoiceField(label='考试ID')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 获取所有考试ID作为选项
        exams = BaseExamConfig.objects.values_list('exam_id', flat=True)
        self.fields['exam_id'].choices = [(exam_id, exam_id) for exam_id in exams]