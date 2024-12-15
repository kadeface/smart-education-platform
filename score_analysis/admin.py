#score_analysis/score_analysis.py:
import json
from django.urls import path ,reverse
from django.template.response import TemplateResponse  # 添加这行导入
from django.db import connection
from django import forms
from django.shortcuts import render
from django.db.models import Q
from django.utils.safestring import mark_safe
from .models.statistics import ExamScoreLines,ScoreRankings, StatisticsExamIndicators
from django.contrib.admin import SimpleListFilter
from django.contrib import admin,messages
from django.shortcuts import redirect
from .models.base import BaseExamConfig,BaseSubjectConfig
from .services.ranking_service import RankingService
from .models.source import ScoreStudentBasic
from .services.statistics_service import BaseStatisticsService
from django.db.models import Subquery, OuterRef
import logging
# 获取 logger 实例
logger = logging.getLogger('django')  # 使用 Django 的默认 logger
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
    change_list_template = 'score_analysis/score_analysis/scorerankings/change_list.html'
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
            return redirect('score_analysis:score_analysis_scorerankings_changelist')

        try:
            service = RankingService()
            if service.generate_rankings(exam_id):
                self.message_user(request, "排名生成成功！")
                # 直接返回到列表页
                return redirect('score_analysis:score_analysis_scorerankings_changelist')
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





@admin.register(StatisticsExamIndicators)
class StatisticsExamIndicatorsAdmin(admin.ModelAdmin):
    """统计指标管理"""
    print("StatisticsExamIndicatorsAdmin 类被加载")  # 添加这行
    #change_list_template = 'admin/score_analysis/statisticsexamindicators/exam_list.html'
    list_display = ['exam_id', 'exam_time', 'has_statistics', 'get_action_button']

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        """获取所有有成绩的考试"""
        # 1. 从成绩表获取所有考试ID
        exams_with_scores = list(ScoreStudentBasic.objects.values_list('exam_id', flat=True).distinct())

        # 2. 获取现有的统计记录，并关联考试名称
        # 只获取总分记录，避免重复显示
        existing_stats = StatisticsExamIndicators.objects.filter(
            exam_id__in=exams_with_scores,
            select_type='理科',
            level_type='city',
            subject_id='total_score'  # 只显示总分记录
        ).annotate(
            exam_name=Subquery(
                BaseExamConfig.objects.filter(
                    exam_id=OuterRef('exam_id')
                ).values('exam_name')[:1]
            )
        )

        # 3. 如果没有统计记录，为所有考试创建初始记录
        if not existing_stats.exists():
            stats_to_create = []
            for exam_id in exams_with_scores:
                stats_to_create.append(
                    StatisticsExamIndicators(
                        exam_id=exam_id,
                        select_type='理科',
                        level_type='city',
                        subject_id='total_score'  # 确保新建记录是总分
                    )
                )
            if stats_to_create:
                StatisticsExamIndicators.objects.bulk_create(stats_to_create)
                # 重新查询，包含考试名称
                return StatisticsExamIndicators.objects.filter(
                    exam_id__in=exams_with_scores,
                    select_type='理科',
                    level_type='city',
                    subject_id='total_score'  # 只返回总分记录
                ).annotate(
                    exam_name=Subquery(
                        BaseExamConfig.objects.filter(
                            exam_id=OuterRef('exam_id')
                        ).values('exam_name')[:1]
                    )
                )

        return existing_stats

    def exam_id(self, obj):
        """获取考试名称"""
        return getattr(obj, 'exam_name', obj.exam_id)

    exam_id.short_description = '考试名称'


    def exam_time(self, obj):
        """从考试名称中提取时间"""
        """从考试ID中提取时间"""
        if obj.exam_id and len(obj.exam_id) >= 6:
            year = obj.exam_id[:4]  # 取前4位作为年份
            month = obj.exam_id[4:6]  # 取第5-6位作为月份
            result = f"{year}年{month}月"
            return result
        return ''

    exam_time.short_description = '考试时间'


    def has_statistics(self, obj):
        """是否已生成统计"""
        try:
            # 检查是否存在统计数据
            has_stats = StatisticsExamIndicators.objects.filter(
                exam_id=obj.exam_id,
                subject_id='total_score',  # 检查总分统计
                student_count__gt=0  # 确保 student_count 大于 0
            ).exists()

            if has_stats:
                return mark_safe('<span style="color: green;">✓</span>')
            return mark_safe('<span style="color: red;">✗</span>')
        except Exception as e:
            logger.error(f"检查统计状态失败: {str(e)}")
            return mark_safe('<span style="color: red;">✗</span>')

    has_statistics.short_description = '已生成统计'

    def get_action_button(self, obj):
        """获取操作按钮"""
        try:
            # 检查是否存在有效的统计数据
            has_stats = StatisticsExamIndicators.objects.filter(
                exam_id=obj.exam_id,
                subject_id='total_score',
                student_count__gt=0
            ).exists()

            button_text = "重新统计" if has_stats else "生成统计"

            # 生成统计按钮
            generate_url = reverse(
                'admin:score_analysis_statisticsexamindicators_generate_statistics',
                args=[obj.exam_id]
            )

            buttons = [
                f'<a class="button" style="background-color: #79aec8; padding: 5px 10px; '
                f'color: white; text-decoration: none; border-radius: 4px; margin-right: 5px;" '
                f'href="{generate_url}">{button_text}</a>'
            ]

            if has_stats:
                # 查看结果按钮
                view_url = reverse(
                    'admin:score_analysis_statisticsexamindicators_view_statistics',
                    args=[obj.exam_id]
                )
                buttons.append(
                    f'<a class="button" style="background-color: #417690; padding: 5px 10px; '
                    f'color: white; text-decoration: none; border-radius: 4px;" '
                    f'href="{view_url}">查看结果</a>'
                )

            return mark_safe(''.join(buttons))
        except Exception as e:
            logger.error(f"生成操作按钮失败: {str(e)}")
            return "操作失败"

    get_action_button.short_description = '操作'

    def generate_statistics(self, request, exam_id):
        """生成统计数据"""
        try:
            print(f"开始生成统计数据: exam_id={exam_id}")
            service = BaseStatisticsService()

            # 解析考试ID获取考试级别
            exam_parts = exam_id.split('-')
            if len(exam_parts) < 2:
                raise ValueError(f"无效的考试ID格式: {exam_id}")

            exam_level = exam_parts[1].upper()  # DIST 或 CITY

            # 删除旧的统计数据
            StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                subject_id__isnull=True
            ).delete()

            if exam_level == 'CITY':
                # 市级考试需要生成市级和区县级统计
                # 1. 生成市级统计
                service.generate_all_statistics(exam_id=exam_id, select_type='理科', level_type='city', request=request)
                service.generate_all_statistics(exam_id=exam_id, select_type='文科', level_type='city', request=request)

                # 2. 生成区县级统计
                service.generate_all_statistics(exam_id=exam_id, select_type='理科', level_type='district',
                                                request=request)
                service.generate_all_statistics(exam_id=exam_id, select_type='文科', level_type='district',
                                                request=request)

                messages.success(request, f'考试 {exam_id} 的市级和区县级统计数据已生成')

            elif exam_level == 'DIST':
                # 区县考试只生成区县级统计
                service.generate_all_statistics(exam_id=exam_id, select_type='理科', level_type='district',
                                                request=request)
                service.generate_all_statistics(exam_id=exam_id, select_type='文科', level_type='district',
                                                request=request)

                messages.success(request, f'考试 {exam_id} 的区县级统计数据已生成')

            else:
                raise ValueError(f"未知的考试级别: {exam_level}")
            return redirect('admin:score_analysis_statisticsexamindicators_view_statistics',
                          exam_id=exam_id)


        except Exception as e:
            print(f"生成统计失败: {str(e)}")
            messages.error(request, f'考试 {exam_id} 统计数据生成失败: {str(e)}')
            return redirect('admin:score_analysis_statisticsexamindicators_changelist')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            # 生成统计的URL
            path('generate-statistics/<str:exam_id>/',
                 self.admin_site.admin_view(self.generate_statistics),
                 name='score_analysis_statisticsexamindicators_generate_statistics'),

            # 查看统计结果的URL
            path('view-statistics/<str:exam_id>/',
                 self.admin_site.admin_view(self.view_statistics),
                 name='score_analysis_statisticsexamindicators_view_statistics'),
        ]
        return custom_urls + urls

    def view_statistics(self, request, exam_id):
        """查看统计结果页面"""
        try:
            # 1. 获取考试基本信息
            exam = BaseExamConfig.objects.filter(exam_id=exam_id).first()
            if not exam:
                raise ValueError(f"未找到考试ID: {exam_id}")

            # 2. 获取理科和文科的统计数据
            science_stats = StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                select_type='理科',
                subject_id='total_score',  # 修改这里，使用 total_score
                #level_type='city'
                student_count__gt=0
            ).first()

            arts_stats = StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                select_type='文科',
                subject_id='total_score',  # 修改这里，使用 total_score
                #level_type='city'
                student_count__gt=0
            ).first()

            # 3. 处理理科和文科的学校分布数据
            science_summary = self._process_school_distribution(
                science_stats.school_distribution if science_stats else None
            )
            arts_summary = self._process_school_distribution(
                arts_stats.school_distribution if arts_stats else None
            )
            #4.处理分数线分布情况
            science_score_lines = self._score_line_distribution(science_stats)
            arts_score_lines = self._score_line_distribution(arts_stats)

            #5处理排名分布情况
            science_rankings = self._process_rank_distribution(science_stats)
            arts_rankings = self._process_rank_distribution(arts_stats)

            science_rankings = dict(sorted(
                science_rankings.items(),
                key=lambda x: x[1]['top_10'],
                reverse=True
            ))

            arts_rankings = dict(sorted(
                arts_rankings.items(),
                key=lambda x: x[1]['top_10'],
                reverse=True
            ))
            #6处理四分位数分析
            science_quartiles = self._process_quartile_analysis(science_stats, 'science')
            arts_quartiles = self._process_quartile_analysis(arts_stats, 'arts')
            context = {
                'title': f'{exam.exam_name} - 统计结果',
                'exam_id': exam_id,
                'exam_name': exam.exam_name,
                'science_summary': science_summary,
                'arts_summary': arts_summary,
                'science_score_lines': science_score_lines,
                'arts_score_lines': arts_score_lines,
                'science_rankings': science_rankings,  # 添加排名数据
                'arts_rankings': arts_rankings,      # 添加排名数据
                'science_quartiles': science_quartiles,  # 添加四分位数数据
                'arts_quartiles': arts_quartiles,# 添加四分位数数据
                **self.admin_site.each_context(request),
            }
            #3 获取文科理科的分数线数据

            return render(
                request,
                'admin/score_analysis/statisticsexamindicators/generate_stats.html',
                context
            )

        except Exception as e:
            logger.error(f"获取统计数据失败: {str(e)}")
            messages.error(request, f'获取统计数据失败: {str(e)}')
            return redirect('admin:score_analysis_statisticsexamindicators_changelist')
    #区县学校分数线分布情况
    def _process_school_distribution(self, school_distribution_json):
        """处理学校分布数据"""
        if not school_distribution_json:
            return {
                'school_count': 0,
                'student_count': 0,
                'mean_score': 0,
                'max_score': 0,
                'top_school': "暂无数据"
            }

        # 解析JSON数据
        schools_data = json.loads(school_distribution_json) if isinstance(school_distribution_json,
                                                                          str) else school_distribution_json

        # 计算基础统计数据
        total_students = 0
        weighted_sum = 0
        max_score = 0
        top_school = "暂无数据"

        for school, data in schools_data.items():
            school_count = data['count']
            total_students += school_count
            weighted_sum += data['mean'] * school_count

            if data['max_score'] > max_score:
                max_score = data['max_score']
                top_school = school

        return {
            'school_count': len(schools_data),
            'student_count': total_students,
            'mean_score': round(weighted_sum / total_students, 2) if total_students > 0 else 0,
            'max_score': max_score,
            'top_school': top_school
        }
    #分数线达线情况
    def _score_line_distribution(self, stats_obj):
        """处理分数线分布数据"""
        if not stats_obj or not stats_obj.threshold_stats:
            return {}

        try:
            thresholds = json.loads(stats_obj.threshold_stats)
            # 按照line值从高到低排序
            sorted_thresholds = dict(sorted(
                thresholds.items(),
                key=lambda x: float(x[1].get('line', 0)),
                reverse=True
            ))
            return sorted_thresholds
        except Exception as e:
            logger.error(f"解析threshold_stats失败: {str(e)}")
            return {}
    #各校的排名分布
    def _process_rank_distribution(self, stats):
        # 从stats中获取rank_distribution并解析JSON
        print("原始数据:", stats.rank_distribution)
        rank_data = json.loads(stats.rank_distribution)
        print("解析后数据:", rank_data)

        # 获取所有学校
        schools = set()
        for rank_group in rank_data.values():
            schools.update(rank_group.keys())

        # 为每个学校创建完整的排名数据
        school_rankings = {school: {
            'top_10': 0,
            'top_20': 0,
            'top_50': 0,
            'top_100': 0,
            'top_200': 0,
            'top_500': 0,
            'top_1250': 0
        } for school in schools}

        # 填充数据
        for rank_level, school_data in rank_data.items():
            for school, count in school_data.items():
                school_rankings[school][rank_level] = count
        print("处理后的数据:", school_rankings)
        return school_rankings
    #四分位分布情况
    def _process_quartile_analysis(self, stats, subject_type='science'):
        """处理四分位分析数据"""
        if not stats:
            return {}

        # 定义所有需要分析的科目
        base_subjects = {
            'total_score': '总分',
            'chinese': '语文',
            'math': '数学',
            'english': '英语',
            'chemistry': '化学',
            'biology': '生物',
            'politics': '政治',
            'geography': '地理'
        }

        # 根据文理科添加特定科目
        if subject_type == 'science':
            base_subjects['physics'] = '物理'
        elif subject_type == 'arts':
            base_subjects['history'] = '历史'

        quartile_data = {}

        # 获取每个科目的统计数据
        for subject_code, subject_name in base_subjects.items():
            subject_stats = StatisticsExamIndicators.objects.filter(
                exam_id=stats.exam_id,
                select_type=stats.select_type,
                subject_id=subject_code,
                student_count__gt=0
            ).first()

            if subject_stats:
                quartile_data[subject_name] = {
                    'mean': subject_stats.mean_score,
                    'max': subject_stats.max_score,
                    'q80': subject_stats.q80_score,
                    'median': subject_stats.median_score,
                    'q20': subject_stats.q20_score,
                    'q10': subject_stats.q10_score
                }

        return quartile_data
    def _prepare_subject_data(self, stats, score_lines, select_type):
        """准备学科统计数据"""
        if not stats:
            return {}

        # 1. 获取最高分学校
        school_distribution = stats.school_distribution or {}
        top_school = "暂无数据"
        if school_distribution:
            top_scores = sorted(
                [(school, data.get('max_score', 0))
                 for school, data in school_distribution.items()],
                key=lambda x: x[1],
                reverse=True
            )
            if top_scores:
                top_school = top_scores[0][0]

        # 2. 准备基础数据
        data = {
            # 基本信息 - 直接使用数据库字段
            'school_count': len(school_distribution),
            'student_count': stats.student_count,
            'mean_score': float(stats.mean_score) if stats.mean_score else 0,
            'max_score': float(stats.max_score) if stats.max_score else 0,
            'min_score': float(stats.min_score) if stats.min_score else 0,
            'std_dev': float(stats.std_dev) if stats.std_dev else 0,
            'top_school': top_school,

            # 分数线和上线数据
            'excellent_rate': float(stats.excellent_rate) if stats.excellent_rate else 0,
            'pass_rate': float(stats.pass_rate) if stats.pass_rate else 0,
            'low_score_rate': float(stats.low_score_rate) if stats.low_score_rate else 0,
        }

        # 添加分数线数据
        for line_type, score in score_lines.items():
            data[f'{line_type}'] = score
            if stats.threshold_stats and line_type in stats.threshold_stats:
                data[f'{line_type}_count'] = stats.threshold_stats[line_type].get('count', 0)
                data[f'{line_type}_rate'] = stats.threshold_stats[line_type].get('rate', 0)

        # 3. 处理学校分布数据
        school_stats = []
        for school_name, school_data in school_distribution.items():
            school_info = {
                'name': school_name,
                'student_count': school_data.get('student_count', 0),
                'max_score': school_data.get('max_score', 0),
                'min_score': school_data.get('min_score', 0),
                'mean_score': school_data.get('mean_score', 0),
                'mean_rank': school_data.get('mean_rank', 0),
            }

            # 添加各分数线上线数据
            threshold_stats = school_data.get('threshold_stats', {})
            for line_type in score_lines.keys():
                line_stats = threshold_stats.get(line_type, {})
                school_info[f'{line_type}_count'] = line_stats.get('count', 0)
                school_info[f'{line_type}_rate'] = line_stats.get('rate', 0)

            school_stats.append(school_info)

        # 按平均分排序
        school_stats.sort(key=lambda x: x['mean_score'], reverse=True)
        data['school_stats'] = school_stats

        # 4. 处理排名分布数据
        rank_stats = {
            'thresholds': {},
            'total': {},
            'schools': {}
        }

        # 处理各个排名段的分布
        rank_fields = {
            'top10': 'top_10_distribution',
            'top20': 'top_20_distribution',
            'top50': 'top_50_distribution',
            'top100': 'top_100_distribution',
            'top200': 'top_200_distribution',
            'top500': 'top_500_distribution',
            'top1250': 'top_1250_distribution'
        }

        for rank_key, field_name in rank_fields.items():
            distribution = getattr(stats, field_name) or {}
            if distribution:
                rank_stats['thresholds'][rank_key] = distribution.get('min_score', 0)
                rank_stats['total'][rank_key] = distribution.get('count', 0)

        data['rank_stats'] = rank_stats

        # 5. 处理四分位数据
        data.update({
            'q80_score': float(stats.q80_score) if stats.q80_score else 0,
            'median_score': float(stats.median_score) if stats.median_score else 0,
            'q20_score': float(stats.q20_score) if stats.q20_score else 0,
            'q10_score': float(stats.q10_score) if stats.q10_score else 0,
        })

        return data
    # 新增：查看统计结果的方法
    def statistics_result(self, request, exam_id):
        """查看统计结果"""
        try:
            # 1. 获取统计数据
            print(f"正在查找考试ID: {exam_id} 的统计数据")  # 调试信息

            stats_list = StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                subject_id='total_score'
            )

            print(f"找到的统计数据数量: {stats_list.count()}")  # 调试信息

            if not stats_list.exists():
                messages.error(request, f'未找到考试 {exam_id} 的统计数据')
                return redirect('admin:score_analysis_statisticsexamindicators_changelist')

            # 分别获取理科和文科的统计数据
            science_stats = stats_list.filter(select_type='理科').first()
            arts_stats = stats_list.filter(select_type='文科').first()

            print(f"理科统计数据: {science_stats}")  # 调试信息
            print(f"文科统计数据: {arts_stats}")  # 调试信息

            # 获取分数线数据
            score_lines = self.get_score_lines(exam_id)
            print(f"分数线数据: {score_lines}")  # 调试信息

            # 2. 准备上下文数据
            context = {
                'exam_id': exam_id,
                'title': f'考试 {exam_id} 统计结果',
                'science_data': self._prepare_subject_data(
                    science_stats,
                    score_lines.get('理科', {}),
                    '理科'
                ) if science_stats else None,
                'arts_data': self._prepare_subject_data(
                    arts_stats,
                    score_lines.get('文科', {}),
                    '文科'
                ) if arts_stats else None,
                **self.admin_site.each_context(request),
            }

            # 3. 渲染结果页面
            return render(
                request,
                'admin/score_analysis/statisticsexamindicators/generate_stats.html',
                context
            )

        except Exception as e:
            logger.error(f"查看统计结果失败: {str(e)}")
            print(f"错误详情: {str(e)}")  # 调试信息
            messages.error(request, f'查看统计结果失败: {str(e)}')
            return redirect('admin:score_analysis_statisticsexamindicators_changelist')

    def get_score_lines(self, exam_id):
        """从数据库获取分数线数据"""
        try:
            print(f"正在获取考试ID: {exam_id} 的分数线数据")  # 调试信息

            # 获取所有分数线数据
            lines = ExamScoreLines.objects.filter(exam_id=exam_id)
            print(f"找到的分数线数据数量: {lines.count()}")  # 调试信息

            # 初始化默认分数线数据结构
            score_lines = {
                '理科': {
                    'qb_line': 0,
                    '985_line': 0,
                    '211_line': 0,
                    'tk_line': 0,
                    'bk_line': 0,
                    'zk_line': 0
                },
                '文科': {
                    'qb_line': 0,
                    '985_line': 0,
                    '211_line': 0,
                    'tk_line': 0,
                    'bk_line': 0,
                    'zk_line': 0
                }
            }

            # 如果有数据，更新默认值
            if lines.exists():
                # 转换分数线类型名称为代码中使用的键名
                line_type_map = {
                    'C9层': 'qb_line',
                    '985层': '985_line',
                    '211层': '211_line',
                    '双一流层': 'tk_line',
                    '本科层': 'bk_line',
                    '优分层': 'zk_line'
                }

                # 更新分数线数据
                for line in lines:
                    key = line_type_map.get(line.line_type)
                    if key and line.select_type in score_lines:
                        score_lines[line.select_type][key] = float(line.score)
                        print(f"更新分数线: {line.select_type} - {line.line_type} - {line.score}")  # 调试信息

            print(f"最终分数线数据: {score_lines}")  # 调试信息
            return score_lines

        except Exception as e:
            logger.error(f"获取分数线数据失败: {str(e)}")
            print(f"获取分数线数据出错: {str(e)}")  # 调试信息

            # 返回默认值
            return {
                '理科': {
                    'qb_line': 0,
                    '985_line': 0,
                    '211_line': 0,
                    'tk_line': 0,
                    'bk_line': 0,
                    'zk_line': 0
                },
                '文科': {
                    'qb_line': 0,
                    '985_line': 0,
                    '211_line': 0,
                    'tk_line': 0,
                    'bk_line': 0,
                    'zk_line': 0
                }
            }