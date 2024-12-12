#from django.contrib import score_analysis
import numpy as np
import pandas as pd
# Register your models here.
from django.contrib import admin
from django.urls import path, reverse
from django.shortcuts import render, redirect
from django.contrib import messages
from django import forms
from .models import ScoreStudentBasic, StudentMapping, BaseExamConfig
from django.utils.html import format_html
from .models import ExamUpload
from score_processor.services.score_processor import ScoreProcessorService
from django.core.files.storage import FileSystemStorage
from .forms import ScoreUploadForm
from .services.data_cleaner import DataCleanerService
from .services.student_mapper import StudentMapperService
from score_analysis.services.ranking_service import RankingService
class ExamInfoAdmin(admin.ModelAdmin):
    list_display = ('exam_id', 'exam_name', 'exam_date', 'exam_type', 'status')
    list_filter = ('exam_type', 'status')
    search_fields = ('exam_id', 'exam_name')

@admin.register(ScoreStudentBasic)
class ScoreStudentBasicAdmin(admin.ModelAdmin):
    list_display = ['exam_id', 'student_id', 'student_name', 'school_name',
                    'class_field', 'chinese', 'math', 'english','physics','history','chemistry','biology','geography','politics']
    list_filter = ['exam_id', 'select_type', 'school_name']
    search_fields = ['student_name', 'student_id', 'school_name']

class StudentMappingAdmin(admin.ModelAdmin):
    list_display = ('exam_id','unified_id', 'original_student_id', 'student_name', 'school_name', 'class_name')
    list_filter = ('exam_id','school_name' )
    search_fields = ('unified_id', 'student_name', 'school_name')
# 先检查是否已注册，如果是则取消注册
if admin.site.is_registered(ExamUpload):
    admin.site.unregister(ExamUpload)


@admin.register(ExamUpload)
class ExamUploadAdmin(admin.ModelAdmin):
    list_display = ['exam_id', 'uploaded_at', 'get_status', 'error_message']
    list_filter = ['status']
    search_fields = ['exam_id']
    readonly_fields = ['uploaded_at', 'status', 'error_message']
    change_list_template = 'admin/score_processor/examupload/upload_list.html'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['upload_form'] = ScoreUploadForm()
        return super().changelist_view(request, extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('upload/',
                 self.admin_site.admin_view(self.upload_scores),
                 name='score_processor_examupload_upload'),
            path('preview/<int:upload_id>/',
                 self.admin_site.admin_view(self.preview_scores),
                 name='score_processor_examupload_preview'),
            path('process/<int:upload_id>/',
                 self.admin_site.admin_view(self.process_scores),
                 name='score_processor_examupload_process'),
            path('clean/<int:upload_id>/',
                 self.admin_site.admin_view(self.clean_data),
                 name='score_processor_examupload_clean'),
            path('mapping/<int:upload_id>/',
                 self.admin_site.admin_view(self.generate_mapping),
                 name='score_processor_examupload_mapping'),
        ]
        return custom_urls + urls

    def get_status(self, obj):
        status_colors = {
            'PENDING': 'orange',
            'PROCESSING': 'blue',
            'COMPLETED': 'green',
            'FAILED': 'red'
        }
        color = status_colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_status_display()
        )

    get_status.short_description = '状态'

    def upload_scores(self, request):
        """处理成绩文件上传"""
        upload = None
        if request.method == 'POST':
            form = ScoreUploadForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    # 创建上传记录
                    upload = ExamUpload(
                        file=request.FILES['file'],
                        exam_id=form.cleaned_data['exam_id'],
                        status='PENDING'
                    )
                    upload.save()
                    # 初始化处理器
                    processor = ScoreProcessorService()

                    # 加载并验证文件
                    success, error = processor.load_file(request.FILES['file'])
                    if success:
                        upload.status = 'PROCESSING'
                        upload.save()
                        messages.success(request, "文件上传成功，请预览数据")
                        return redirect('admin:score_processor_examupload_preview', upload_id=upload.id)
                    else:
                        upload.status = 'FAILED'
                        upload.error_message = error
                        upload.save()
                        messages.error(request, f"文件验证失败: {error}")

                except Exception as e:
                    if  upload:
                        upload.status = 'FAILED'
                        upload.error_message = str(e)
                        upload.save()
                    messages.error(request, f"上传失败: {str(e)}")

                return redirect('admin:score_processor_examupload_changelist')
            else:
                # 表单验证失败的处理
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
                return redirect('admin:score_processor_examupload_changelist')

            # POST请求的默认重定向
        return redirect('admin:score_processor_examupload_changelist')
        form = ScoreUploadForm()
        context = {
            'form': form,
            'title': '上传成绩文件',
            'subtitle': '请选择Excel文件并选择考试ID，前提是你要先建立考试',
            'opts': self.model._meta,
            'is_popup': False,
            'has_view_permission': True,
        }
        return render(request, 'score_processor/upload.html', context)

    def preview_scores(self, request, upload_id):
        """预览成绩数据"""
        try:
            upload = self.get_object(request, upload_id)
            processor = ScoreProcessorService()

            # 加载文件
            success, error = processor.load_file(upload.file.path)
            if not success:
                messages.error(request, f"文件加载失败: {error}")
                return redirect('admin:score_processor_examupload_changelist')

            # 获取预览数据
            preview_result = processor.get_preview_data()
            if preview_result:
                context = {
                    'title': '预览成绩数据',
                    'opts': self.model._meta,
                    'data': preview_result['data'],
                    'stats': preview_result['stats'],
                    'upload': upload,
                    'has_view_permission': True,
                }
                return render(request, 'score_processor/preview.html', context)
            else:
                messages.error(request, "预览数据生成失败")

        except Exception as e:
            messages.error(request, f"预览失败: {str(e)}")

        return redirect('admin:score_processor_examupload_changelist')

    def process_scores(self, request, upload_id):
        """处理成绩数据"""
        if request.method == 'POST':
            try:
                upload = self.get_object(request, upload_id)
                processor = ScoreProcessorService()

                # 加载文件
                success, error = processor.load_file(upload.file.path)
                if not success:
                    upload.status = 'FAILED'
                    upload.error_message = f"文件加载失败: {error}"
                    upload.save()
                    messages.error(request, f"文件加载失败: {error}")
                    return redirect('admin:score_processor_examupload_changelist')

                # 处理数据
                result = processor.process_scores(processor.df, upload.id)
                if result['success']:
                    upload.status = 'PROCESSING'  # 改为处理中，因为还要继续处理
                    upload.save()
                    messages.success(request, "成绩处理成功,进入数据清洗阶段")
                    return redirect('admin:score_processor_examupload_clean', upload_id=upload.id)
                else:
                    messages.error(request, f"处理失败: {result['error']}")

            except Exception as e:
                messages.error(request, f"处理失败: {str(e)}")

        return redirect('admin:score_processor_examupload_changelist')

    def clean_data(self, request, upload_id):
        """清洗数据"""
        try:
            upload = self.get_object(request, upload_id)
            processor = ScoreProcessorService()
            cleaner = DataCleanerService()

            if request.method == 'POST':
                # 加载文件
                success, error = processor.load_file(upload.file.path)
                if not success:
                    upload.status = 'FAILED'
                    upload.error_message = error
                    upload.save()
                    messages.error(request, f"文件加载失败: {error}")
                    return redirect('admin:score_processor_examupload_changelist')

                # 清洗数据
                try:
                    result = cleaner.clean_data(processor.df)
                    if result['success']:
                        upload.status = 'PROCESSING'  # 继续处理
                        upload.save()

                        # 将清洗统计转换为普通Python类型
                        cleaning_stats = result['stats']
                        for key, value in cleaning_stats.items():
                            if isinstance(value, np.int64):
                                cleaning_stats[key] = int(value)
                            elif isinstance(value, dict):
                                for k, v in value.items():
                                    if isinstance(v, np.int64):
                                        value[k] = int(v)

                        # 获取有效成绩统计并转换类型
                        score_stats = cleaner.get_valid_scores_stats(result['cleaned_df'])

                        context = {
                            'title': '数据清洗',
                            'subtitle': '数据清洗完成',
                            'opts': self.model._meta,
                            'upload': upload,
                            'has_view_permission': True,
                            'cleaning_stats': cleaning_stats,
                            'score_stats': score_stats,
                        }

                        messages.success(request, "数据清洗完成")
                        return render(request, 'score_processor/cleaning.html', context)
                    else:
                        error_message = result.get('error', '未知错误')
                        upload.status = 'FAILED'
                        upload.error_message = error_message
                        upload.save()
                        messages.error(request, f"清洗失败: {error_message}")
                except Exception as clean_error:
                    upload.status = 'FAILED'
                    upload.error_message = str(clean_error)
                    upload.save()
                    messages.error(request, f"清洗过程出错: {str(clean_error)}")

            # GET请求显示清洗页面
            context = {
                'title': '数据清洗',
                'subtitle': '点击开始清洗按钮进行数据清洗',
                'opts': self.model._meta,
                'upload': upload,
                'has_view_permission': True,
            }
            return render(request, 'score_processor/cleaning.html', context)

        except Exception as e:
            messages.error(request, f"清洗数据失败: {str(e)}")
            return redirect('admin:score_processor_examupload_mapping')

    def generate_mapping(self, request, upload_id):
        """生成统一考号映射"""
        try:
            upload = self.get_object(request, upload_id)
            processor = ScoreProcessorService()
            mapper = StudentMapperService()

            if request.method == 'POST':
                # 加载文件
                success, error = processor.load_file(upload.file.path)
                if not success:
                    messages.error(request, f"文件加载失败: {error}")
                    return redirect('admin:score_processor_examupload_changelist')

                # 生成映射
                result = mapper.process_exam_data(processor.df, upload.exam_id)
                if result['success']:
                    # 更新状态
                    upload.status = 'COMPLETED'
                    upload.save()

                    # 处理预览数据
                    preview_rows = []
                    if isinstance(result.get('preview_df'), pd.DataFrame):
                        df = result['preview_df']
                        if not df.empty:
                            # 选择要显示的列
                            display_columns = ['市区', '学校', '姓名', '考号', '班级',
                                               '语文', '数学', '英语', '统一ID']
                            preview_df = df[display_columns].head(10)

                            # 转换为列表
                            preview_rows = preview_df.to_dict('records')

                    # 准备显示结果
                    context = {
                        'title': '考号映射结果',
                        'subtitle': '统一考号生成完成',
                        'opts': self.model._meta,
                        'upload': upload,
                        'has_view_permission': True,
                        'preview_data': preview_rows,
                        'columns': display_columns,
                        'stats': {
                            '总记录数': result['total_count'],
                            '新生成ID数': result['new_count'],
                            '复用ID数': result['reused_count']
                        }
                    }
                    messages.success(request, "统一考号生成完成")
                    return render(request, 'score_processor/mapping_result.html', context)
                else:
                    upload.status = 'FAILED'
                    upload.error_message = result.get('error', '未知错误')
                    upload.save()
                    messages.error(request, f"生成统一考号失败: {result.get('error', '未知错误')}")
                    return redirect('admin:score_processor_examupload_mapping', upload_id=upload.id)

            # GET请求显示映射页面
            context = {
                'title': '生成统一考号',
                'subtitle': '点击开始按钮生成统一考号',
                'opts': self.model._meta,
                'upload': upload,
                'has_view_permission': True,
            }
            return render(request, 'score_processor/mapping.html', context)

        except Exception as e:
            messages.error(request, f"生成统一考号失败: {str(e)}")
            return redirect('admin:score_processor_examupload_mapping', upload_id=upload.id)

# Register models
admin.site.register(BaseExamConfig, ExamInfoAdmin)
admin.site.register(StudentMapping, StudentMappingAdmin)
