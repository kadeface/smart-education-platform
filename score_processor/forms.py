from django import forms

class ScoreUploadForm(forms.Form):
    file = forms.FileField(label='选择文件')
    exam_id = forms.CharField(label='考试ID', max_length=50)