#from django.contrib import score_analysis
import numpy as np
import pandas as pd
from urllib.parse import quote
from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import ScoreStudentBasic, StudentMapping, BaseExamConfig
from django.utils.html import format_html
from .models import ExamUpload
from score_processor.services.score_processor import ScoreProcessorService
from .forms import ScoreUploadForm
from .services.data_cleaner import DataCleanerService
from .services.MappingGenerator import MappingGenerator
from .services.StudentIDMapper import StudentIDMapper
import io
from django.http import HttpResponse, JsonResponse
from django.template.response import TemplateResponse
from django.db import models
from django.core.cache import cache


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


@admin.register(StudentMapping)
class StudentMappingAdmin(admin.ModelAdmin):
    list_display = ['unified_id', 'exam_id', 'student_name', 'school_name',
                    'class_name', 'match_type', 'is_new']
    list_filter = ['exam_id', 'school_name', 'match_type', 'is_new']
    search_fields = ['unified_id', 'student_name', 'original_student_id']
    date_hierarchy = 'create_time'

    change_list_template = 'admin/score_processor/studentmapping/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('upload/', self.upload_view, name='student-mapping-upload'),
            path('template/', self.download_template, name='student-mapping-template'),
           # path('preview/<str:exam_id>/', self.preview_results, name='student-mapping-preview'),
        ]
        return custom_urls + urls

    def download_template(self, request):
        """下载Excel模板"""
        # 创建模板数据
        template_data = {
            'student_name': ['张三', '李四'],
            'school_name': ['示例中学', '示例中学'],
            'class_name': ['高三(1)班', '高三(2)班'],
            'original_student_id': ['2024001', '2024002'],
            'student_id': ['S20240001', 'S20240002'],  # 可选
            'id_number': ['', ''],  # 可选
        }
        df = pd.DataFrame(template_data)

        # 创建Excel文件
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='数据模板')

            # 获取工作表
            worksheet = writer.sheets['数据模板']

            # 添加说明
            worksheet.insert_rows(0, 5)
            worksheet['A1'] = '填表说明：'
            worksheet['A2'] = '1. student_name, school_name, class_name, original_student_id 为必填项'
            worksheet['A3'] = '2. student_id(学籍号), id_number（身份证号） 为选填项，用于匹配已有统一考号'
            worksheet['A4'] = '3. 请勿修改字段名称'

        # 设置响应头
        output.seek(0)
        response = HttpResponse(output.read(),
                                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=student_mapping_template.xlsx'
        return response

    def upload_view(self, request):
        """处理文件上传"""
        if request.method == 'POST':
            try:
                exam_file = request.FILES['file']
                exam_id = request.POST['exam_id']

                # 实例化处理器
                mapper = StudentIDMapper()

                # 处理数据
                stats = mapper.process_exam_data(exam_file, exam_id)

                # 获取最新10条记录作为预览
                recent_records = StudentMapping.objects.filter(
                    exam_id=exam_id
                ).order_by('-create_time')[:10]

                # 获取统计信息
                db_stats = StudentMapping.objects.filter(exam_id=exam_id).aggregate(
                    total=models.Count('id'),
                    new=models.Count('id', filter=models.Q(is_new=True)),
                    student_id_match=models.Count('id', filter=models.Q(match_type='student_id')),
                    id_number_match=models.Count('id', filter=models.Q(match_type='id_number')),
                    name_school_match=models.Count('id', filter=models.Q(match_type='name_school'))
                )

                # 添加成功消息
                messages.success(request, '文件处理成功！')

                # 返回同一个页面，但包含处理结果
                context = {
                    **self.admin_site.each_context(request),
                    'title': '上传学生数据',
                    'exam_ids': BaseExamConfig.objects.filter(
                        status='published'
                    ).values_list('exam_id', 'exam_name').order_by('-exam_id'),
                    'opts': self.model._meta,
                    'stats': db_stats,
                    'preview': recent_records,
                    'success': True
                }
                return TemplateResponse(
                    request,
                    'admin/score_processor/studentmapping/upload.html',
                    context
                )

            except Exception as e:
                messages.error(request, f'处理失败: {str(e)}')

        # GET 请求或处理失败时显示上传表单
        context = {
            **self.admin_site.each_context(request),
            'title': '上传学生数据',
            'exam_ids': BaseExamConfig.objects.filter(
                status='published'
            ).values_list('exam_id', 'exam_name').order_by('-exam_id'),
            'opts': self.model._meta,
        }
        return TemplateResponse(
            request,
            'admin/score_processor/studentmapping/upload.html',
            context
        )
    def preview_results(self, request, exam_id):
        """预览处理结果"""
        # 获取统计信息
        stats = StudentMapping.objects.filter(exam_id=exam_id).aggregate(
            total=models.Count('id'),
            new=models.Count('id', filter=models.Q(is_new=True)),
            student_id_match=models.Count('id', filter=models.Q(match_type='student_id')),
            id_number_match=models.Count('id', filter=models.Q(match_type='id_number')),
            name_school_match=models.Count('id', filter=models.Q(match_type='name_school'))
        )

        # 获取最新10条记录
        recent_records = StudentMapping.objects.filter(exam_id=exam_id).order_by('-create_time')[:10]

        return JsonResponse({
            'stats': stats,
            'preview': list(recent_records.values(
                'unified_id', 'student_name', 'school_name', 'class_name', 'match_type'
            ))
        })
# 先检查是否已注册，如果是则取消注册
if admin.site.is_registered(ExamUpload):
    admin.site.unregister(ExamUpload)


@admin.register(ExamUpload)
class ExamUploadAdmin(admin.ModelAdmin):
    list_display = ['exam_id', 'uploaded_at', 'get_status', 'error_message', 'get_school_level']
    list_filter = ['status', 'school_level']  # 添加学段过滤
    search_fields = ['exam_id']
    readonly_fields = ['uploaded_at', 'status', 'error_message', 'school_level']
    change_list_template = 'admin/score_processor/examupload/upload_list.html'
    ordering = ['-uploaded_at']  # 负号表示倒序，最新的在最上面

    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)
        # 基础字段映射（所有学段通用）
        self.base_mapping = {
            '市(区)': 'district_name',
            '学校': 'school_name',
            '姓名': 'student_name',
            '考号': 'exam_number',
            '班级': 'class_name',
            '总分': 'total_score'
        }

        # 不同学段的科目映射
        self.subject_mapping = {
            'P': {  # 小学
                '语文': 'chinese',
                '数学': 'math',
                '英语': 'english',
                '科学': 'science'
            },
            'M': {  # 初中
                '语文': 'chinese',
                '数学': 'math',
                '英语': 'english',
                '物理': 'physics',
                '化学': 'chemistry',
                '政治': 'politics',
                '历史': 'history',
                '生物': 'biology',
                '地理': 'geography'
            },
            'H': {  # 高中
                '语文': 'chinese',
                '数学': 'math',
                '英语': 'english',
                '物理': 'physics',
                '化学': 'chemistry',
                '政治': 'politics',
                '历史': 'history',
                '生物': 'biology',
                '地理': 'geography'
            }
        }
        super().__init__(model, admin_site)

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
        print("=== URL Patterns ===")
        for url in custom_urls + urls:
            print(f"Pattern: {url.pattern}, Name: {getattr(url, 'name', 'unnamed')}")
        return  custom_urls+urls

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

    def get_base_subject_config(self, obj):
        """显示考试配置信息"""
        if obj.base_subject_config:
            return f"{obj.base_subject_config.exam_name} ({obj.base_subject_config.get_semester_display()})"  # 使用 exam_name
        return '-'
    get_base_subject_config.short_description = '考试配置'

    def get_school_level(self, obj):
        """显示学段信息"""
        level_names = {
            'H': '高中',
            'M': '初中',
            'P': '小学'
        }
        return level_names.get(obj.school_level, '未知')

    get_school_level.short_description = '学段'


    def upload_scores(self, request):
        """处理成绩文件上传和模板下载"""
        print("处理成绩文件请求")
        # 处理模板下载请求
        if request.method == 'GET' and request.GET.get('action') == 'download_template':
            try:
                school_level = request.GET.get('school_level')
                if not school_level:
                    messages.error(request, "请选择学段")
                    return redirect('admin:score_processor_examupload_changelist')

                if school_level not in ['P', 'M', 'H']:
                    messages.error(request, "无效的学段")
                    return redirect('admin:score_processor_examupload_changelist')

                print(f"开始生成{school_level}学段的模板")
                mapping_generator = MappingGenerator()
                return mapping_generator.generate_score_template(school_level)
            except Exception as e:
                print(f"模板下载失败: {str(e)}")
                messages.error(request, str(e))
                return redirect('admin:score_processor_examupload_changelist')


        """处理成绩文件上传"""
        print("上传文件入口")
        upload = None  # 在最外层初始化 upload 变量

        if request.method == 'POST':
            form = ScoreUploadForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    # 从表单获取考试配置对象
                    base_subject_config = form.cleaned_data['base_subject_config']
                    exam_id = base_subject_config.exam_id

                    # 检查是否已存在相同考试ID的上传记录
                    if ExamUpload.objects.filter(exam_id=exam_id, status='PROCESSING').exists():
                        messages.error(request, f"考试 {exam_id} 已有正在处理的记录")
                        return redirect('admin:score_processor_examupload_changelist')

                    # 创建上传记录
                    upload = ExamUpload(
                        file=request.FILES['file'],
                        exam_id=exam_id,
                        base_subject_config=base_subject_config,
                        school_level=exam_id[12],  # 确保索引正确
                        status='PENDING'
                    )
                    upload.save()

                    # 初始化处理器
                    processor = ScoreProcessorService(
                        exam_id=exam_id,
                        base_subject_config=base_subject_config
                    )

                    # 加载并验证文件
                    success, error = processor.load_file(request.FILES['file'])
                    if success:
                        upload.status = 'PROCESSING'
                        upload.save()
                        messages.success(request, "文件上传成功，请预览数据")
                        # 成功后直接跳转到预览页面
                        return redirect('admin:score_processor_examupload_preview', upload_id=upload.id)
                    else:
                        upload.status = 'FAILED'
                        upload.error_message = error
                        upload.save()
                        messages.error(request, f"文件验证失败: {error}")
                        return redirect('admin:score_processor_examupload_changelist')

                except IndexError:
                    # 处理考试ID格式错误
                    if upload:
                        upload.status = 'FAILED'
                        upload.error_message = "考试ID格式错误"
                        upload.save()
                    messages.error(request, "考试ID格式错误，无法获取学段信息")
                    return redirect('admin:score_processor_examupload_changelist')

                except Exception as e:
                    # 处理其他所有异常
                    if upload:
                        upload.status = 'FAILED'
                        upload.error_message = str(e)
                        upload.save()
                    messages.error(request, f"上传失败: {str(e)}")
                    # 打印详细错误信息以便调试
                    import traceback
                    print(traceback.format_exc())
                    return redirect('admin:score_processor_examupload_changelist')

            else:
                # 表单验证失败
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
                return redirect('admin:score_processor_examupload_changelist')

        # GET请求直接返回
        return redirect('admin:score_processor_examupload_changelist')
    def preview_scores(self, request, upload_id):
        """预览成绩数据"""
        try:


            upload = self.get_object(request, upload_id)
            base_subject_config = BaseExamConfig.objects.get(exam_id=upload.exam_id)

            # 初始化处理器（传入考试ID和科目配置）
            processor = ScoreProcessorService(
                exam_id=upload.exam_id,
                base_subject_config=base_subject_config
            )

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
                    'school_level': upload.school_level,  # 添加学段信息
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
                    raise ValueError(f"文件加载失败: {error}")

                # 清洗数据
                try:
                    result = cleaner.clean_data(processor.df)
                    if result['success']:
                        cache_key = f"cleaned_data_{upload_id}"
                        cache.set(cache_key, result['cleaned_df'].to_dict('records'), timeout=3600)  # 1小时过期
                        upload.status = 'PROCESSING'
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

                        # 获取有效成绩统计
                        score_stats = cleaner.get_valid_scores_stats(result['cleaned_df'])

                        context = {
                            **self.admin_site.each_context(request),  # 添加管理站点上下文
                            'title': '数据清洗',
                            'subtitle': '数据清洗完成',
                            'opts': self.model._meta,
                            'upload': upload,
                            'has_view_permission': True,
                            'cleaning_stats': cleaning_stats,
                            'score_stats': score_stats,
                        }

                        messages.success(request, "数据清洗完成")
                        return TemplateResponse(
                            request,
                            'admin/score_processor/studentmapping/cleaning_result.html',  # 修改模板路径
                            context
                        )
                    else:
                        error_message = result.get('error', '未知错误')
                        upload.status = 'FAILED'
                        upload.error_message = error_message
                        upload.save()
                        messages.error(request, f"清洗失败: {error_message}")
                        return redirect('admin:score_processor_examupload_mapping', upload_id=upload.id)

                except Exception as clean_error:
                    upload.status = 'FAILED'
                    upload.error_message = str(clean_error)
                    upload.save()
                    messages.error(request, f"清洗过程出错: {str(clean_error)}")
                    return redirect('admin:score_processor_examupload_mapping', upload_id=upload.id)

            # GET请求显示清洗页面
            context = {
                **self.admin_site.each_context(request),  # 添加管理站点上下文
                'title': '数据清洗',
                'subtitle': '点击开始清洗按钮进行数据清洗',
                'opts': self.model._meta,
                'upload': upload,
                'has_view_permission': True,
            }
            return TemplateResponse(
                request,
                'admin/score_processor/studentmapping/cleaning.html',  # 修改模板路径
                context
            )

        except Exception as e:
            messages.error(request, f"清洗数据失败: {str(e)}")
            return redirect('admin:score_processor_examupload_mapping', upload_id=upload_id)

    def generate_mapping(self, request, upload_id):
        """生成统一考号映射"""
        try:
            upload = self.get_object(request, upload_id)
            mapper = MappingGenerator()  # 使用新的 MappingGenerator 类

            if request.method == 'POST':
                # 检查上传状态
                if upload.status != 'PROCESSING':
                    messages.error(request, "请先完成数据清洗")
                    return redirect('admin:score_processor_examupload_clean', upload_id=upload.id)

                # 从缓存获取已清洗的数据
                cache_key = f"cleaned_data_{upload_id}"
                cleaned_data = cache.get(cache_key)

                if not cleaned_data:
                    messages.error(request, "清洗数据已过期，请重新清洗")
                    return redirect('admin:score_processor_examupload_clean', upload_id=upload.id)

                # 将数据转换为DataFrame（如果还不是DataFrame）
                if not isinstance(cleaned_data, pd.DataFrame):
                    cleaned_data = pd.DataFrame(cleaned_data)

                # 打印调试信息
                print(f"\n=== 数据处理调试信息 ===")
                print(f"DataFrame列名: {cleaned_data.columns.tolist()}")
                print(f"数据形状: {cleaned_data.shape}")
                print(f"考试ID: {upload.exam_id}")

                # 使用新的 generate 方法
                success = mapper.generate(
                    cleaned_data=cleaned_data,
                    exam_id=upload.exam_id
                )

                # 处理完成后删除缓存
                cache.delete(cache_key)

                if success:
                    # 更新状态
                    upload.status = 'COMPLETED'
                    upload.save()

                    # 获取最新的10条记录作为预览
                    preview_records = StudentMapping.objects.filter(
                        exam_id=upload.exam_id
                    ).order_by('-create_time')[:10]

                    # 准备显示结果
                    context = {
                        **self.admin_site.each_context(request),
                        'title': '考号映射结果',
                        'subtitle': '统一考号生成完成',
                        'opts': self.model._meta,
                        'upload': upload,
                        'has_view_permission': True,
                        'preview_data': preview_records
                    }
                    messages.success(request, "统一考号生成完成")
                    return TemplateResponse(
                        request,
                        'admin/score_processor/studentmapping/mapping_result.html',
                        context
                    )
                else:
                    upload.status = 'FAILED'
                    upload.error_message = '生成统一考号失败'
                    upload.save()
                    messages.error(request, "生成统一考号失败")
                    return redirect('admin:score_processor_examupload_changelist')

            # GET请求显示映射页面
            context = {
                **self.admin_site.each_context(request),
                'title': '生成统一考号',
                'subtitle': '点击开始按钮生成统一考号',
                'opts': self.model._meta,
                'upload': upload,
                'has_view_permission': True,
            }
            return TemplateResponse(
                request,
                'admin/score_processor/studentmapping/mapping.html',
                context
            )

        except Exception as e:
            print(f"\n=== 生成统一考号出错 ===")
            print(f"错误信息: {str(e)}")
            import traceback
            print("详细错误:")
            print(traceback.format_exc())

            messages.error(request, f"生成统一考号失败: {str(e)}")
            return redirect('admin:score_processor_examupload_changelist')


