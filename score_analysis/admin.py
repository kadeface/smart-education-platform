#score_analysis/admin.py:
from django.urls import path
from django.template.response import TemplateResponse  # 添加这行导入
from django.db import connection
from django import forms
from django.db.models.fields import CharField
from django.db.models import F, Count, Value
from .models.statistics import ExamScoreLines,ScoreRankings
from .models.base import BaseExamConfig
from django.contrib.admin import SimpleListFilter
from django.contrib import admin
from django.shortcuts import render, redirect
from django.contrib import messages
from score_processor.models import BaseExamConfig,BaseSubjectConfig # 从score_processor导入模型
from .services.ranking_service import RankingService

from django.db.models import Q
class ExamScoreLinesForm(forms.ModelForm):
    # 自定义表单字段
    exam_id = forms.ChoiceField(label='考试ID')

    class Meta:
        model = ExamScoreLines
        fields = ['exam_id', 'select_type', 'line_type', 'score']

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
    list_display = ['exam_id', 'select_type', 'line_type', 'score', 'create_time', 'update_time']
    list_filter = ['select_type', 'line_type']
    search_fields = ['exam_id']
    readonly_fields = ['create_time', 'update_time']  # 修改为实际存在的字段

    fieldsets = (
        ('基本信息', {
            'fields': ('exam_id', 'select_type', 'line_type', 'score')
        }),
        ('时间信息', {
            'fields': ('create_time', 'update_time'),
            'classes': ('collapse',)
        })
    )


# 如果已经注册，先取消注册
try:
    admin.site.unregister(ScoreRankings)
except:
    pass


class SubjectFilter(SimpleListFilter):
    title = '科目'
    parameter_name = 'subject'

    def lookups(self, request, model_admin):
        return [
            ('total_score', '总分'),
            ('chinese', '语文'),
            ('math', '数学'),
            ('english', '英语'),
            ('physics', '物理'),
            ('chemistry', '化学'),
            ('biology', '生物'),
            ('history', '历史'),
            ('geography', '地理'),
            ('politics', '政治'),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(subject=self.value())
        return queryset


class StreamTypeFilter(SimpleListFilter):
    title = '类别'
    parameter_name = 'select_type'

    def lookups(self, request, model_admin):
        return [
            ('文科', '文科'),
            ('理科', '理科'),

        ]

    def queryset(self, request, queryset):
        """根据选择的选项过滤数据"""
        if self.value():
            # 添加调试信息
            print(f"\n=== 类别过滤 ===")
            print(f"选择的类别: {self.value()}")
            print(f"过滤前记录数: {queryset.count()}")

            # 检查数据库中的实际值
            #select_types = queryset.values_list('select_type', flat=True).distinct()
            #print(f"数据库中的类别值: {list(select_types)}")


            filtered_queryset = queryset.filter(select_type=self.value())
            #print(f"过滤后记录数: {filtered_queryset.count()}")

            return filtered_queryset
        return queryset


class DistrictFilter(SimpleListFilter):
    title = '区域'
    parameter_name = 'level_type'  # 改为直接过滤 level_type

    def lookups(self, request, model_admin):
        """
        返回市级和所有区县作为过滤选项
        """
        # 首先添加市级选项
        options = [('city', '地市级')]

        # 获取所有区县
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT district_name 
                FROM score_student_basic 
                WHERE district_name IS NOT NULL 
                ORDER BY district_name
            """)
            districts = cursor.fetchall()

        # 区县名称直接作为 level_type 的值
        options.extend((district[0], district[0]) for district in districts)
        return options

    def queryset(self, request, queryset):
        """
        根据选择的区域过滤数据
        """
        if not self.value():
            return queryset

        # 直接过滤 level_type
        return queryset.filter(level_type=self.value())



@admin.register(ScoreRankings)
class ScoreRankingsAdmin(admin.ModelAdmin):
    list_display = [
        'get_exam_name',
        'get_student_name',
        'get_school_name',
        'get_subject_name',
        'get_stream_type',
        'get_level_type',
        'get_raw_score',
        'get_raw_score_rank',

    ]
    list_filter = [SubjectFilter, StreamTypeFilter,  DistrictFilter]
    search_fields = ['unified_student_id', 'student_name', 'school_name']
    list_per_page = 10
    ordering = ['subject', 'select_type', 'raw_score_rank']
    change_list_template = 'admin/score_analysis/scorerankings/change_list.html'
    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)
        # 初始化时从数据库获取科目配置
        self.subject_names = {
            'total': '总分'  # 总分特殊处理
        }
        try:
            subjects = BaseSubjectConfig.objects.all()
            for subject in subjects:
                self.subject_names[subject.subject_id] = subject.subject_name
        except:
            # 如果获取失败，使用默认映射
            self.subject_names.update({
                'chinese': '语文',
                'math': '数学',
                'english': '英语',
                'physics': '物理',
                'chemistry': '化学',
                'biology': '生物',
                'history': '历史',
                'geography': '地理',
                'politics': '政治'
            })


    def get_exam_name(self, obj):
        return f"{obj.exam.exam_name} ({obj.exam.exam_id})"

    get_exam_name.short_description = '考试'
    get_exam_name.admin_order_field = 'exam__exam_name'

    def get_raw_score(self, obj):
        """显示原始分数"""
        return obj.raw_score
    get_raw_score.short_description = '分数'
    get_raw_score.admin_order_field = 'raw_score'

    def get_raw_score_rank(self, obj):
        """显示排名"""
        return obj.raw_score_rank
    get_raw_score_rank.short_description = '排名'
    get_raw_score_rank.admin_order_field = 'raw_score_rank'

    def get_student_name(self, obj):
        return obj.student_name

    get_student_name.short_description = '姓名'
    get_student_name.admin_order_field = 'student_name'

    def get_school_name(self, obj):
        return obj.school_name

    get_school_name.short_description = '学校'
    get_school_name.admin_order_field = 'school_name'

    def get_subject_name(self, obj):
        """显示科目中文名称"""
        subject_names = {
            'total_score': '总分',
            'chinese': '语文',
            'math': '数学',
            'english': '英语',
            'physics': '物理',
            'chemistry': '化学',
            'biology': '生物',
            'history': '历史',
            'geography': '地理',
            'politics': '政治'
        }
        # 如果是字符串，直接查字典
        if isinstance(obj.subject, str):
            return subject_names.get(obj.subject, obj.subject)
        # 如果是外键对象，获取 subject_id
        elif hasattr(obj.subject, 'subject_id'):
            return subject_names.get(obj.subject.subject_id, str(obj.subject))
        # 其他情况返回原值的字符串形式
        return str(obj.subject)

    get_subject_name.short_description = '科目'
    get_subject_name.admin_order_field = 'subject'

    def get_stream_type(self, obj):
        """显示中文类别名称"""
        select_types = {
            'arts': '文科',
            'science': '理科',

        }
        return obj.select_type

    get_stream_type.short_description = '类别'
    get_stream_type.admin_order_field = 'select_type'

    def get_level_type(self, obj):
        """显示考试级别中文名称"""
        level_types = {
            'city': '地市级',
            'district': '区县级',
            'school': '校级'
        }
        return level_types.get(obj.level_type, obj.level_type)
    get_level_type.short_description = '排名级别'
    get_level_type.admin_order_field = 'level_type'

    def add_view(self, request, form_url='', extra_context=None):
        """处理生成排名的视图"""
        if request.method == 'POST':
            exam_id = request.POST.get('exam_id')
            if exam_id:
                try:
                    service = RankingService()
                    if service.generate_rankings(exam_id):
                        self.message_user(request, "排名生成成功！")
                        return redirect('..')  # 返回列表页
                    else:
                        self.message_user(request, "生成排名失败", level=messages.ERROR)
                except Exception as e:
                    self.message_user(request, f"生成排名时出错: {str(e)}", level=messages.ERROR)
            else:
                self.message_user(request, "请选择考试！", level=messages.ERROR)

        # 获取考试列表供选择
        try:
            exams = BaseExamConfig.objects.values(
                'exam_id',
                'exam_name'
            ).order_by('-exam_date')

            context = {
                'title': '选择考试生成排名',
                'exams': exams,
                'has_permission': True,
                'opts': self.model._meta,
            }

            return TemplateResponse(request, 'score_analysis/generate_rankings.html', context)

        except Exception as e:
            self.message_user(request, f"获取考试列表失败: {str(e)}", level=messages.ERROR)
            return redirect('..')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('generate/<str:exam_id>/',
                 self.admin_site.admin_view(self.generate_rankings),
                 name='generate_rankings'),
        ]
        return custom_urls + urls

    def generate_rankings(self, request, exam_id):
        """处理排名生成"""
        try:
            service = RankingService()
            if service.generate_rankings(exam_id):
                self.message_user(request, "排名生成成功！")
            else:
                self.message_user(request, "生成排名失败", level=messages.ERROR)
        except Exception as e:
            self.message_user(request, f"生成排名时出错: {str(e)}", level=messages.ERROR)

        return redirect('..')
    def process_ranking_generation(self, request):
        """处理排名生成的逻辑"""
        print("\n=== 开始生成排名 ===")
        exam_id = request.POST.get('exam_id')

        if not exam_id:
            self.message_user(request, '请选择考试', messages.ERROR)
            return redirect('admin:score_analysis_scorerankings_changelist')

        try:
            service = RankingService()
            if service.generate_rankings(exam_id):
                self.message_user(request, "排名生成成功！")
                # 直接返回到列表页
                return redirect('admin:score_analysis_scorerankings_changelist')
            else:
                self.message_user(request, "生成排名失败", level=messages.ERROR)
                return redirect('.')
        except Exception as e:
            self.message_user(request, f"生成排名时出错: {str(e)}", level=messages.ERROR)
            return redirect('.')

    def get_ordering(self, request):
        """确保默认排序"""
        return ['subject', 'select_type', 'raw_score_rank', 'unified_student_id']

    def get_queryset(self, request):
        """确保不会过度限制基础查询集"""
        queryset = super().get_queryset(request)
        return queryset

    def get_search_results(self, request, queryset, search_term):
        """优化搜索功能"""
        #print(f"\n=== 搜索调试信息 ===")
        #print(f"搜索词: {search_term}")
        #print(f"原始查询数量: {queryset.count()}")

        # 如果有搜索词
        if search_term:
            queryset = queryset.filter(
                Q(student_name__icontains=search_term) |
                Q(unified_student_id__icontains=search_term) |
                Q(school_name__icontains=search_term) |
                Q(exam_id__exact=search_term)  # 对于 exam_id 使用精确匹配
            ).distinct()

        #print(f"搜索后数量: {queryset.count()}")
        #print(f"SQL查询: {queryset.query}")

        return queryset, False

        # 确保没有默认的过滤器

    def get_list_filter(self, request):
        return [SubjectFilter, StreamTypeFilter, DistrictFilter]




