#score_analysis/score_analysis.py:
import json

from django.http import HttpResponseRedirect, JsonResponse
from django.urls import path ,reverse
from django.template.response import TemplateResponse
from django.db import connection, transaction
from django import forms
from django.shortcuts import render
from django.db.models import Q, F
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models.statistics import ExamScoreLines, ScoreRankings, StatisticsExamIndicators, ExamLevelAnalysisTask, \
    ExamLevelAnalysisConfig
from django.contrib.admin import SimpleListFilter
from django.contrib import admin,messages
from django.shortcuts import redirect
from .models.base import BaseExamConfig,BaseSubjectConfig
from .services.ranking_service import RankingService
from .models.source import ScoreStudentBasic
from .services.statistics.statistics_generator import StatisticsGenerator
from django.db.models import Subquery, OuterRef
import logging
from .models.region import LayerAnalysis
from .services.region.layer_analysis import LayerAnalysisService
from .services.region.layer_view import LayerViewService
from .models.Tracking import TrackingRecord
from .services.tracking.tracking_generator import TrackingGenerator

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
            ('未确定', '未确定'),
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

            return TemplateResponse(request, 'admin/score_analysis/scorerankings/generate_rankings.html', context)

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
    """基础统计指标生成语管理"""

    #change_list_template = 'admin/score_analysis/statisticsexamindicators/exam_list.html'
  #  list_display = ['exam_id', 'exam_time', 'has_statistics', 'get_action_button']

    list_display = ('exam_id', 'exam_name', 'exam_date', 'has_statistics', 'actions_column')

    def get_queryset(self, request):
        """获取所有考试列表"""
        queryset = BaseExamConfig.objects.all().order_by('-exam_id')
        # 将 exam_id 作为 indicator_id
        return queryset.annotate(indicator_id=F('exam_id'))

    def exam_name(self, obj):
        """获取考试名称"""
        return obj.exam_name

    def exam_date(self, obj):
        """获取考试日期"""
        return obj.exam_date

    def has_statistics(self, obj):
        """是否已生成统计"""
        return StatisticsExamIndicators.objects.filter(
            exam_id=obj.exam_id,
            subject_id='total_score'
        ).exists()

    def actions_column(self, obj):
        """操作列"""
        return format_html(
            '<a class="button" href="{}">重新统计</a> '
            '<a class="button" href="{}">查看结果</a>',
            reverse('admin:score_analysis_statisticsexamindicators_generate_statistics', args=[obj.exam_id]),
            reverse('score_analysis:statistics_preview', args=[obj.exam_id, 'basic'])
        )

    exam_name.short_description = '考试名称'
    exam_date.short_description = '考试日期'
    has_statistics.short_description = '已生成统计'
    has_statistics.boolean = True
    actions_column.short_description = '操作'

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
            config_exists = ExamLevelAnalysisConfig.objects.filter(exam_id=exam_id).exists()
            if not config_exists:
                # 获取考试信息以确定配置类型
                exam = BaseExamConfig.objects.get(exam_id=exam_id)

                messages.error(request, f'考试 {exam_id} 未配置分数线，请先配置分数线')
                # 重定向到分数线配置页面
                return redirect('admin:score_analysis_examlevelanalysisconfig_changelist')
            print(f"开始生成统计数据: exam_id={exam_id}")
            service = StatisticsGenerator()

            # 解析考试ID获取考试级别
            exam_parts = exam_id.split('-')
            if len(exam_parts) < 2:
                raise ValueError(f"无效的考试ID格式: {exam_id}")

            # 删除旧的统计数据
            StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                subject_id__isnull=True
            ).delete()

            service.generate_exam_statistics(exam_id=exam_id)
        # 生成成功，添加成功消息
            messages.success(request, f'考试 {exam_id} 统计数据生成成功')

            # 重定向到预览页面
            return redirect('score_analysis:statistics_preview', exam_id=exam_id,module_type='basic')
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
            # 1. 获取考试层级信息
            level_type, districts = self._get_level_type(exam_id)
            logger.info(f"考试 {exam_id} 的统计层级为: {level_type}, 包含区县: {districts}")

            if not level_type:
                raise ValueError(f"无法确定考试 {exam_id} 的统计层级")

            # 2. 获取理科和文科的统计数据
            science_stats = StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                select_type='理科',
                subject_id='total_score',
                level_type=level_type,
                student_count__gt=0
            ).first()

            arts_stats = StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                select_type='文科',
                subject_id='total_score',
                level_type=level_type,
                student_count__gt=0
            ).first()

            # 3. 获取考试名称
            exam_name = BaseExamConfig.objects.filter(exam_id=exam_id).values_list('exam_name', flat=True).first()

            # 4. 处理各类统计数据
            context = {
                'title': f'{exam_name} - 统计结果',
                'exam_id': exam_id,
                'exam_name': exam_name,
                'level_type': level_type,

                # 统计数据
                'science_summary': self._process_summary_data(science_stats),
                'arts_summary': self._process_summary_data(arts_stats),
                'science_score_lines': self._score_line_distribution(science_stats),
                'arts_score_lines': self._score_line_distribution(arts_stats),
                'science_rankings': dict(sorted(
                    self._process_rank_distribution(science_stats).items(),
                    key=lambda x: x[1]['top_10'],
                    reverse=True
                )) if science_stats else {},
                'arts_rankings': dict(sorted(
                    self._process_rank_distribution(arts_stats).items(),
                    key=lambda x: x[1]['top_10'],
                    reverse=True
                )) if arts_stats else {},
                'science_quartiles': self._process_quartile_analysis(science_stats, 'science'),
                'arts_quartiles': self._process_quartile_analysis(arts_stats, 'arts'),
                'science_school_means': self._process_school_subject_means(science_stats, 'science'),
                'arts_school_means': self._process_school_subject_means(arts_stats, 'arts'),

                **self.admin_site.each_context(request),
            }

            # 5. 如果是地市级考试，获取区县数据
            if level_type == '地市级' and districts:
                district_data = {}
                for district in districts:
                    district_stats_science = StatisticsExamIndicators.objects.filter(
                        exam_id=exam_id,
                        select_type='理科',
                        subject_id='total_score',
                        level_type=district,
                        student_count__gt=0
                    ).first()

                    district_stats_arts = StatisticsExamIndicators.objects.filter(
                        exam_id=exam_id,
                        select_type='文科',
                        subject_id='total_score',
                        level_type=district,
                        student_count__gt=0
                    ).first()

                    district_data[district] = {
                        'science': self._process_summary_data(district_stats_science),
                        'arts': self._process_summary_data(district_stats_arts)
                    }

                context['district_data'] = district_data

            return render(
                request,
                'admin/score_analysis/statisticsexamindicators/exam_overview_with_subjects.html',
                context
            )

        except Exception as e:
            logger.error(f"获取统计数据失败: {str(e)}")
            messages.error(request, f'获取统计数据失败: {str(e)}')
            return redirect('admin:score_analysis_statisticsexamindicators_changelist')
    #获取考试的类型（江门市统考或者开平市统考）
    def _get_exam_statistics(self, exam_id):
        """获取考试统计数据"""

        # 判断考试类型并返回对应的level_type
        if 'CITY' in exam_id:
            return 'city'  # 地市级统考
        else:
            return '开平市'  # 默认为区县级别（开平市）
    #获取考试的类型（江门市统考或者区县市统考）
    def _get_level_type(self, exam_id):
        """
        根据考试ID获取统计层级信息

        Args:
            exam_id: str, 考试ID (例如: JM-CITY-2023-1)

        Returns:
            tuple: (level_type, districts)
                - level_type: str, '地市级' 或 具体区县名
                - districts: list, 如果是地市级考试则返回所有区县列表，否则返回None
        """
        logger.info(f"开始确定考试 {exam_id} 的统计层级")

        try:
            if 'CITY' in exam_id:
                # 对于市级考试，获取所有区县
                districts = StatisticsExamIndicators.objects.filter(
                    exam_id=exam_id,
                    subject_id='total_score',
                    student_count__gt=0
                ).exclude(
                    level_type='地市级'
                ).values_list('level_type', flat=True).distinct()

                return '地市级', list(districts)
            else:
                # 对于区县级考试
                district = StatisticsExamIndicators.objects.filter(
                    exam_id=exam_id,
                    subject_id='total_score',
                    student_count__gt=0
                ).values_list('level_type', flat=True).first()

                if district:
                    logger.info(f"区县级考试: {district}")
                    return district, None
                else:
                    logger.error(f"未找到考试 {exam_id} 的统计记录")
                    return None, None

        except Exception as e:
            logger.error(f"获取考试层级失败: {str(e)}")
            return None, None
        #综述数据

    def _process_summary_data(self, stats):
        """
        处理综述数据，生成完整的统计信息
        Args:
            stats: StatisticsExamIndicators 对象
        Returns:
            dict: 处理后的统计数据
        """
        if not stats:
            logger.warning("没有找到统计数据")
            return {}

        try:
            # 1. 安全地解析JSON数据
            try:
                school_distribution = json.loads(stats.school_distribution) if stats.school_distribution else {}
                school_count = len(school_distribution)
            except json.JSONDecodeError:
                logger.warning(f"解析school_distribution失败: {stats.school_distribution}")
                school_count = 0

            try:
                thresholds = json.loads(stats.threshold_stats) if stats.threshold_stats else {}
            except json.JSONDecodeError:
                logger.warning(f"解析threshold_stats失败: {stats.threshold_stats}")
                thresholds = {}

            # 2. 构建基础查询
            query = ScoreStudentBasic.objects.filter(
                exam_id=stats.exam_id
            )

            # 添加select_type过滤（如果存在）
            if hasattr(stats, 'select_type') and stats.select_type:
                query = query.filter(select_type=stats.select_type)

            # 根据层级添加筛选条件
            if hasattr(stats, 'level_type'):
                if stats.level_type == '地市级':
                    if hasattr(stats, 'max_score'):
                        query = query.filter(total_score=stats.max_score)
                elif stats.level_type == '区县级':
                    if hasattr(stats, 'district_name'):
                        query = query.filter(district_name=stats.district_name)
                elif hasattr(stats, 'school_name'):  # 学校级
                    query = query.filter(school_name=stats.school_name)

            # 3. 获取最高分记录
            top_student = query.order_by('-total_score').values(
                'student_id',
                'student_name',
                'school_name',
                'total_score',
                'district_name'
            ).first()

            # 4. 处理分数线数据
            score_lines = {}
            name_mapping = {
                'C9层': 'c9',
                '985层': '985',
                '211层': '211',
                '双一流层': 'dual_first_class',
                '优分层': 'excellent',
                '本科层': 'undergraduate'
            }

            # 安全获取总人数
            total_students = getattr(stats, 'student_count', 0) or 1

            # 处理每个分数线
            for display_name, key in name_mapping.items():
                line_data = thresholds.get(display_name, {})
                count = int(line_data.get('count', 0) or 0)
                rate = (count / total_students) * 100 if total_students > 0 else 0

                score_lines[key] = {
                    'name': display_name,
                    'score': float(line_data.get('line', 0) or 0),
                    'count': count,
                    'rate': round(rate, 2)
                }

                logger.info(f"{display_name} - 人数: {count}, 总人数: {total_students}, 比率: {rate}%")

            # 5. 整理返回数据
            summary_data = {
                'school_count': school_count,
                'student_count': total_students,
                'mean_score': round(float(getattr(stats, 'mean_score', 0) or 0), 2),
                'max_score': float(getattr(stats, 'max_score', 0) or 0),
                'top_school': top_student['school_name'] if top_student else '未知',
                'score_lines': score_lines
            }

            logger.info(
                f"成功处理统计数据: 学校数={school_count}, 学生数={total_students}, "
                f"平均分={summary_data['mean_score']}, 最高分={summary_data['max_score']}, "
                f"第一名学校={summary_data['top_school']}"
            )

            return summary_data

        except Exception as e:
            logger.error(f"处理综述数据失败: {str(e)}")
            logger.exception(e)
            return {}
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
        """处理排名分布数据
        Args:
            stats: StatisticsExamIndicators实例
        Returns:
            dict: {
                '学校A': {'top_10': 5, 'top_20': 8, 'top_50': 10, ...},
                '学校B': {'top_10': 0, 'top_20': 0, 'top_50': 2, ...},  # 没有的排名补0
            }
        """
        try:
            # 检查数据是否存在
            if not stats or not stats.rank_distribution:
                logger.warning("没有排名分布数据")
                return {}

            # 解析JSON数据
            rank_data = json.loads(stats.rank_distribution)

            # 获取school_rankings数据
            school_rankings = rank_data.get('school_rankings', {})

            # 定义所有需要的排名范围
            rank_ranges = ['top_10', 'top_20', 'top_50', 'top_100',
                           'top_200', 'top_500', 'top_1250']

            # 处理每个学校的数据，确保所有排名范围都存在
            processed_rankings = {}
            for school, rankings in school_rankings.items():
                processed_rankings[school] = {
                    rank_range: rankings.get(rank_range, 0)
                    for rank_range in rank_ranges
                }

            # 按top_10人数排序
            sorted_data = dict(sorted(
                processed_rankings.items(),
                key=lambda x: x[1]['top_10'],
                reverse=True
            ))

            return sorted_data

        except Exception as e:
            logger.error(f"处理排名分布数据失败: {str(e)}")
            return {}
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
    #各校的平均分列表
    def _process_school_subject_means(self, stats, exam_type):
        """处理各校各科平均分数据"""
        try:
            if not stats:
                return {'subjects': [], 'schools': []}

            exam_id = stats.exam_id
            select_type = '理科' if exam_type == 'science' else '文科'
            level_type = stats.level_type

            # 获取所有科目的统计数据
            all_stats = StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                select_type=select_type,
                level_type=level_type
            )

            # 打印调试信息
           # logger.info(f"处理{select_type}各校各科平均分数据:")
           # logger.info(f"找到 {all_stats.count()} 个科目的统计数据")

            # 准备数据结构
            schools_data = {}
            subjects_order = []

            # 处理每个科目的数据
            for stat in all_stats:
                subject_name = stat.subject.subject_name
                subjects_order.append(subject_name)

                # 打印当前处理的科目
             #   logger.info(f"处理科目: {subject_name}")

                # 解析school_distribution JSON数据
                try:
                    school_dist = json.loads(stat.school_distribution)
                    logger.info(f"科目 {subject_name} 的学校分布数据: {school_dist}")
                except (json.JSONDecodeError, AttributeError) as e:
                    logger.error(f"解析科目 {subject_name} 的school_distribution失败: {e}")
                    continue

                # 整理每个学校的数据
                for school_name, school_stats in school_dist.items():
                    if school_name not in schools_data:
                        schools_data[school_name] = {
                            'school_name': school_name,
                            'subjects': {}
                        }

                    # 添加该科目的统计数据
                    schools_data[school_name]['subjects'][subject_name] = {
                        'count': school_stats['count'],
                        'mean': school_stats['mean'],
                        'std_dev': school_stats.get('std_dev', 0)
                    }

            # 转换为列表并按总分平均分排序
            schools_list = list(schools_data.values())
            schools_list.sort(
                key=lambda x: x['subjects'].get('总分', {}).get('mean', 0),
                reverse=True
            )

            # 打印最终的数据结构
           # logger.info(f"最终数据结构:")
           # logger.info(f"科目顺序: {subjects_order}")
            #logger.info(f"学校数据示例: {schools_list[0] if schools_list else 'No schools'}")

            return {
                'subjects': subjects_order,
                'schools': schools_list
            }

        except Exception as e:
            logger.error(f"处理学校科目平均分失败: exam_type={exam_type}, error={str(e)}")
            logger.exception("详细错误信息:")
            return {'subjects': [], 'schools': []}


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
                'admin/score_analysis/statisticsexamindicators/exam_overview_with_subjects.html',
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


@admin.register(LayerAnalysis)
class LayerAnalysisAdmin(admin.ModelAdmin):
    """总分层次分析管理"""
    change_list_template = 'admin/score_analysis/layeranalysis/change_list.html'

    def changelist_view(self, request, extra_context=None):
        """自定义列表视图"""
        # 获取所有考试信息，按考试ID降序排序
        exams = BaseExamConfig.objects.all().order_by('-exam_id').values(
            'exam_id',
            'exam_name',
            'exam_date'
        )

        # 获取已生成分层分析的考试ID列表
        analyzed_exams = set(
            LayerAnalysis.objects.values_list('exam_id', flat=True)
            .distinct()
        )

        # 准备考试数据
        exam_list = []
        for exam in exams:
            exam_data = {
                'exam_id': exam['exam_id'],
                'exam_name': exam['exam_name'],
                'exam_date': self._get_exam_date(exam['exam_id']),
                'has_analysis': exam['exam_id'] in analyzed_exams
            }
            exam_list.append(exam_data)

        context = {
            'title': '分层分析管理',
            'exam_list': exam_list,
            'has_add_permission': False,  # 禁用添加按钮
            'has_change_permission': True,
            'has_delete_permission': False,  # 禁用删除按钮
            'has_view_permission': True,
            'opts': self.model._meta,  # 添加模型元数据
            **self.admin_site.each_context(request),
            **(extra_context or {})
        }

        return TemplateResponse(request, self.change_list_template, context)

    def get_urls(self):
        """添加自定义URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                'generate/<str:exam_id>/',
                self.admin_site.admin_view(self.generate_analysis),
                name='layer_analysis_generate'
            ),
            path(
                'view/<str:exam_id>/',
                self.admin_site.admin_view(self.view_analysis),
                name='layer_analysis_view'
            ),
        ]
        return custom_urls + urls

    def generate_analysis(self, request, exam_id):
        """生成分层分析"""
        try:
            service = LayerAnalysisService()
            service.generate_layer_analysis(exam_id=exam_id)
            messages.success(request, f'考试 {exam_id} 的分层分析数据已重新生成')

        except Exception as e:
            messages.error(request, f'生成分层分析失败: {str(e)}')
            logger.error(f"生成分层分析失败: {str(e)}", exc_info=True)

        return redirect('admin:score_analysis_layeranalysis_changelist')

    def view_analysis(self, request, exam_id):
        """查看分层分析结果"""
        try:
            # 检查数据是否存在
            analyses = LayerAnalysis.objects.filter(exam_id=exam_id)
            if not analyses.exists():
                messages.error(request, f'未找到考试 {exam_id} 的分层分析数据')
                return redirect('admin:score_analysis_layeranalysis_changelist')

            # 获取请求参数
            select_type = request.GET.get('select_type', '理科')
            selected_districts = request.GET.getlist('districts')

            # 使用服务类获取数据
            service = LayerViewService()
            exam_info = service.get_exam_info(exam_id)
            district_analysis = service.get_district_analysis(exam_id, select_type)
            school_analysis = service.get_school_analysis(exam_id, select_type, selected_districts)
            all_districts = service.get_all_districts(exam_id)

            # 构建URL
            science_url = f"?select_type=理科"
            liberal_url = f"?select_type=文科"
            if selected_districts:
                for district in selected_districts:
                    science_url += f"&districts={district}"
                    liberal_url += f"&districts={district}"

            context = {
                'title': f'考试 {exam_id} 分层分析结果',
                'exam_id': exam_id,
                'exam_info': exam_info,
                'select_type': select_type,
                'district_analysis': district_analysis,
                'school_analysis': school_analysis,
                'all_districts': all_districts,
                'selected_districts': selected_districts,
                'science_url': science_url,
                'liberal_url': liberal_url,
                'is_city_exam': 'CITY' in exam_id.upper(),
                **self.admin_site.each_context(request),
            }

            return TemplateResponse(
                request,
                'score_analysis/region/layer_analysis.html',
                context
            )

        except Exception as e:
            logger.error(f"查看分析结果失败: {str(e)}", exc_info=True)
            messages.error(request, f'查看分析结果失败: {str(e)}')
            return redirect('admin:score_analysis_layeranalysis_changelist')

    def _get_exam_date(self, exam_id):
        """从考试ID中提取年月"""
        try:
            if exam_id and len(exam_id) >= 6:
                year = exam_id[:4]
                month = exam_id[4:6]
                return f"{year}年{month}月"
        except Exception as e:
            logger.error(f"解析考试日期失败: {str(e)}")
        return ''

    def has_add_permission(self, request):
        """禁用添加功能"""
        return False

    def has_delete_permission(self, request, obj=None):
        """禁用删除功能"""
        return False


@admin.register(TrackingRecord)
class TrackingAdmin(admin.ModelAdmin):

    change_list_template = "admin/tracking/tracking.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('tracking/', self.tracking_view, name='tracking-view'),
            path('tracking/generate/', self.generate_tracking, name='generate-tracking'),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        """重定向到 tracking 视图"""
        print("==== changelist_view called ====")
        return self.tracking_view(request)

    def tracking_view(self, request):
        """显示发展跟踪生成页面"""
        logger.info("Entering tracking_view")  # 调试日志

        # 获取考试列表，按学段和年级分组
        try:
            print("==== exams data:")  # 打印 2
            exams = self.get_exams_by_level()
            logger.info(f"Retrieved exams: {exams}")  # 调试日志
            print("==== exams data:")  # 打印 2
            context = {
                **self.admin_site.each_context(request),
                'title': '发展跟踪生成',
                'exams': exams,
            }
            logger.info("Context prepared")  # 调试日志

            return TemplateResponse(request, "admin/tracking/tracking.html", context)

        except Exception as e:
            logger.error(f"Error in tracking_view: {e}")  # 错误日志
            raise

    def generate_tracking(self, request):
        """处理生成请求"""
        if request.method == 'POST':
            exam_ids = request.POST.getlist('exams')
            generate_t_score = request.POST.get('t_score') == 'on'
            generate_rank = request.POST.get('rank') == 'on'
            force_update = request.POST.get('force_update') == 'true'  # 新增参数

            if not exam_ids:
                messages.error(request, '请选择至少一个考试')
                return self.tracking_view(request)

            try:
                generator = TrackingGenerator()
                existing_exams = []
                success_exams = []

                # 第一次尝试生成
                for exam_id in exam_ids:
                    result = generator.generate(
                        exam_id=exam_id,
                        generate_t_score=generate_t_score,
                        generate_rank=generate_rank
                    )

                    if result == "EXISTS":
                        existing_exams.append(exam_id)
                    else:
                        success_exams.append(exam_id)

                # 如果有已存在数据的考试
                if existing_exams:
                    if not force_update:
                        # 返回确认信息
                        context = {
                            **self.admin_site.each_context(request),
                            'title': '发展跟踪生成',
                            'exams': self.get_exams_by_level(),
                            'existing_exams': existing_exams,
                            'success_exams': success_exams,
                            'generate_t_score': generate_t_score,
                            'generate_rank': generate_rank,
                            'show_confirm': True
                        }
                        return TemplateResponse(request, "admin/tracking/tracking.html", context)
                    else:
                        # 用户确认重新生成
                        for exam_id in existing_exams:
                            generator.generate(
                                exam_id=exam_id,
                                generate_t_score=generate_t_score,
                                generate_rank=generate_rank
                            )
                            success_exams.append(exam_id)

                messages.success(request, f'成功处理 {len(success_exams)} 个考试的发展跟踪数据')

            except Exception as e:
                messages.error(request, f'处理发展跟踪数据时出错: {str(e)}')

            # 重新获取考试列表并返回
            context = {
                **self.admin_site.each_context(request),
                'title': '发展跟踪生成',
                'exams': self.get_exams_by_level(),  # 重新获取考试列表
            }
            return self.tracking_view(request)

    def get_exams_by_level(self):
        """获取按学段和毕业年份分组的考试列表"""
        with connection.cursor() as cursor:
            # 简化SQL，只检查 tracking_records 是否存在记录
            sql = """
                SELECT 
                    e.exam_id,
                    e.exam_name,
                    e.semester,
                    e.exam_type,
                    CASE WHEN tr.exam_id IS NOT NULL THEN 1 ELSE 0 END as has_tracking
                FROM base_exam_config e
                LEFT JOIN (
                    SELECT DISTINCT exam_id 
                    FROM tracking_records
                ) tr ON e.exam_id = tr.exam_id
                WHERE e.status IN ('draft', 'published')
                ORDER BY e.exam_id DESC
            """
            cursor.execute(sql)
            rows = cursor.fetchall()

            # 初始化结果字典：学段 -> 毕业年份 -> 考试列表
            exams = {
                'H': {},  # 高中
                'M': {},  # 初中
                'P': {}  # 小学
            }

            for row in rows:
                exam_id, exam_name, semester, exam_type, has_tracking = row

                # 确定学段
                if semester and semester.startswith('H'):
                    level = 'H'
                elif semester and semester.startswith('M'):
                    level = 'M'
                elif semester and semester.startswith('P'):
                    level = 'P'
                else:
                    continue

                # 从考试ID中提取毕业年份（最后4位）
                grad_year = exam_id[-4:]

                # 初始化该学段下的毕业年份（如果不存在）
                if grad_year not in exams[level]:
                    exams[level][grad_year] = []

                # 添加考试信息，包含跟踪状态
                exams[level][grad_year].append({
                    'id': exam_id,
                    'name': f"{exam_name} ({exam_type})",
                    'has_tracking': bool(has_tracking)
                })

            # 对每个学段内的毕业年份进行排序
            for level in exams:
                exams[level] = dict(sorted(exams[level].items(), reverse=True))

            return exams


@admin.register(ExamLevelAnalysisConfig)
class ExamLevelAnalysisConfigAdmin(admin.ModelAdmin):
    """设置考试线和排名统计"""


    SCIENCE_ARTS_TYPES = ['文科', '理科']
    GENERAL_TYPE = '不确定'
    DIVIDED_SEMESTERS = ['H1-2', 'H2-1', 'H2-2', 'H3-1', 'H3-2']  # 需要分科的学期
    change_list_template = 'admin/exam_level/config_list.html'
    change_form_template = 'admin/exam_level/config_detail.html'
    class Media:
        js = (
            'admin/js/jquery.min.js',  # 确保 jQuery 加载
            'admin/js/jquery.init.js',
            'admin/js/core.js',
            'admin/js/config.js',  # 我们的自定义 JS
        )
    def get_urls(self):
        """自定义URL模式"""
        from django.urls import path

        info = self.model._meta.app_label, self.model._meta.model_name

        return [
            path('<str:exam_id>/basic_stats/',
                 self.admin_site.admin_view(self.basic_stats_view),
                 name='%s_%s_basic_stats' % info),
            path('<str:exam_id>/',
                 self.admin_site.admin_view(self.exam_config_list),
                 name='%s_%s_exam_configs' % info),
            path('',
                 self.admin_site.admin_view(self.changelist_view),
                 name='%s_%s_changelist' % info),
            path('<str:exam_id>/reset/',
                 self.admin_site.admin_view(self.reset_exam_configs),
                 name='%s_%s_reset_exam' % info),
            path('<str:exam_id>/<str:select_type>/',
                 self.admin_site.admin_view(self.config_detail_view),
                 name='%s_%s_config_detail' % info),
            path('<str:exam_id>/',
                 self.admin_site.admin_view(self.config_detail_view),
                 name='%s_%s_save_config' % info),

        ]

    def exam_config_list(self, request, exam_id):
        """显示单个考试的所有配置"""
        try:
            exam = BaseExamConfig.objects.get(exam_id=exam_id)

            context = {
                'title': f'{exam.exam_name}配置',
                'opts': self.model._meta,
                'app_label': self.model._meta.app_label,
                'exam': exam,
                'has_change_permission': self.has_change_permission(request),
                'is_popup': False,
                'media': self.media,
            }

            if exam.semester in self.DIVIDED_SEMESTERS:
                context['select_types'] = self.SCIENCE_ARTS_TYPES
            else:
                context['select_types'] = [self.GENERAL_TYPE]

            return TemplateResponse(
                request,
                'admin/exam_level/exam_config_list.html',
                context
            )

        except BaseExamConfig.DoesNotExist:
            messages.error(request, f'考试 {exam_id} 不存在')
            return HttpResponseRedirect('../')
    def _validate_select_type(self, exam, select_type):
        """验证分科类型是否合法"""
        if exam.semester in self.DIVIDED_SEMESTERS:
            # 需要分科的学期，只能选择文科或理科
            return select_type in self.SCIENCE_ARTS_TYPES
        else:
            # 不分科的学期，只能选择未分科
            return select_type == self.GENERAL_TYPE

    def changelist_view(self, request, extra_context=None):
        """配置列表视图"""
        context = dict(
            title='考试分层分析配置',
            opts=self.model._meta,
            app_label=self.model._meta.app_label,
            exams=BaseExamConfig.objects.all().order_by('-exam_id'),
            # 添加这些上下文变量
            divided_semesters=self.DIVIDED_SEMESTERS,  # ['高一下', '高二', '高三']
            science_arts_types=self.SCIENCE_ARTS_TYPES,  # ['文科', '理科']
            general_type=self.GENERAL_TYPE,  # '未分科'
            has_change_permission=self.has_change_permission(request),
            is_popup=False,
            cl=None,
            media=self.media,
            has_add_permission=self.has_add_permission(request),
            has_delete_permission=self.has_delete_permission(request),
        )

        # 获取现有配置
        configs = ExamLevelAnalysisConfig.objects.all()
        config_map = {}
        for config in configs:
            if config.exam_id not in config_map:
                config_map[config.exam_id] = {}
            config_map[config.exam_id][config.select_type] = config

        context['config_map'] = config_map

        return TemplateResponse(request, self.change_list_template, context)

    def config_detail_view(self, request, exam_id, select_type):
        """配置详情视图"""
        try:
            exam = BaseExamConfig.objects.get(exam_id=exam_id)
            # 如果没有指定 select_type，根据学期自动选择
            if not select_type:
                if exam.semester in self.DIVIDED_SEMESTERS:
                    # 对于需要分科的学期，默认显示文科配置
                    select_type = self.SCIENCE_ARTS_TYPES[0]  # '文科'
                else:
                    # 对于不分科的学期，显示未分科配置
                    select_type = self.GENERAL_TYPE  # '未分科'

                # 重定向到完整的 URL
                return HttpResponseRedirect(
                    reverse(
                        'admin:%s_%s_config_detail' % (
                            self.model._meta.app_label,
                            self.model._meta.model_name
                        ),
                        args=[exam_id, select_type]
                    )
                )

            config, created = ExamLevelAnalysisConfig.objects.get_or_create(
                exam_id=exam_id,
                select_type=select_type,
                defaults={
                    'name': f'{exam.exam_name}-{select_type}配置',
                    'rank_ranges': {
                        '市级': [10, 20, 50, 100, 200, 500],
                        'default': [10, 50, 100]
                    },
                    'score_lines': self._get_default_score_lines(select_type)
                }
            )

            if request.method == 'POST':
                try:
                    # 处理表单提交
                    rank_ranges = {}
                    for area in request.POST.getlist('area_name'):
                        ranges = request.POST.getlist(f'rank_ranges_{area}')
                        rank_ranges[area] = [int(r) for r in ranges if r]

                    # 根据分科类型处理不同的配置
                    if exam.semester in self.DIVIDED_SEMESTERS:
                        score_lines = {}
                        for type_ in request.POST.getlist('score_type'):
                            value = request.POST.get(f'score_value_{type_}')
                            if value:
                                score_lines[type_] = float(value)
                        config.score_lines = score_lines
                    else:
                        # 未分科的情况下处理百分比配置
                        score_lines = {}
                        for type_ in ['优秀', '合格', '低分']:
                            value = request.POST.get(f'score_value_{type_}')
                            if value:
                                score_lines[type_] = float(value) / 100  # 转换为小数
                        config.score_lines = score_lines

                    config.rank_ranges = rank_ranges
                    config.save()

                    messages.success(request, '配置已更新')
                    return HttpResponseRedirect('../')

                except ValueError as e:
                    messages.error(request, f'数值格式错误：{str(e)}')
                except Exception as e:
                    messages.error(request, f'更新失败：{str(e)}')

            context = {
                'title': f'{exam.exam_name} - {select_type}配置',
                'opts': self.model._meta,
                'app_label': self.model._meta.app_label,
                'exam': exam,
                'config': config,
                'is_divided': exam.semester in self.DIVIDED_SEMESTERS,  # 是否分科
                'has_change_permission': self.has_change_permission(request),
                'is_popup': False,
                'media': self.media,
                'has_add_permission': self.has_add_permission(request),
                'has_delete_permission': self.has_delete_permission(request),
                # 添加额外的上下文数据
                'score_types': {
                    True: ['C9', '985', '211', '特控', '本科', '专科'],  # 分科的分数线类型
                    False: ['优秀', '合格', '低分']  # 未分科的分数线类型
                }[exam.semester in self.DIVIDED_SEMESTERS],
                'rank_areas': ['市级', 'default'],  # 排名区域
            }

            return TemplateResponse(
                request,
                'admin/exam_level/config_detail.html',
                context
            )

        except BaseExamConfig.DoesNotExist:
            messages.error(request, f'考试 {exam_id} 不存在')
            return HttpResponseRedirect('../')
        except Exception as e:
            messages.error(request, str(e))
            return HttpResponseRedirect('../')

    def _get_default_score_lines(self, select_type):
        """获取默认分数线配置"""
        if select_type in ['文科', '理科']:
            return {
                'C9': 680,
                '985': 600,
                '211': 580,
                '特控': 530,
                '本科': 420,
                '专科': 270
            }
        else:
            return {
                '优秀': 0.20,  # 前20%
                '合格': 0.80,  # 前80%
                '低分': 0.95  # 后5%
            }
    def _get_default_rank_ranges(self):
        """获取默认排名范围配置"""
        return {
            '市级': [10, 50, 100, 200, 500, 1000, 3000, 9600],
            'default': [10, 50, 100, 400, 1250]
        }

    def reset_exam_configs(self, request, exam_id):
        """重置单个考试的所有配置"""

        try:
            with transaction.atomic():  # 添加事务处理
                exam = BaseExamConfig.objects.select_for_update().get(exam_id=exam_id)  # 添加行锁
                # 使用统一的数字列表格式
                default_rank_ranges = self._get_default_rank_ranges()
                # 根据学期确定需要重置的分科类型
                if exam.semester in self.DIVIDED_SEMESTERS:
                    select_types = self.SCIENCE_ARTS_TYPES  # 文科、理科
                else:
                    select_types = [self.GENERAL_TYPE]  # 未分科

                # 只重置配置表中的数据
                for select_type in select_types:
                    try:
                        config, created = ExamLevelAnalysisConfig.objects.update_or_create(
                            exam_id=exam_id,
                            select_type=select_type,
                            defaults={
                                'name': f'{exam.exam_name}-{select_type}配置',
                                'rank_ranges': {
                                    '市级': [10, 50, 100, 200, 500, 1200, 3000, 9600],
                                    'default': [10, 50, 100, 400, 1250]
                                },
                                'score_lines': self._get_default_score_lines(select_type)
                            }
                        )
                        logger.info(f'已重置配置: {exam.exam_name}-{select_type}')
                    except Exception as e:
                        logger.error(f'重置{select_type}配置失败: {str(e)}')
                        raise

                # 删除不需要的配置
                ExamLevelAnalysisConfig.objects.filter(
                    exam_id=exam_id
                ).exclude(
                    select_type__in=select_types
                ).delete()

                messages.success(request, f'考试 {exam.exam_name} 的配置已重置为默认值')

        except BaseExamConfig.DoesNotExist:
            logger.error(f'考试不存在: {exam_id}')
            messages.error(request, f'考试 {exam_id} 不存在')
        except Exception as e:
            logger.error(f'重置考试配置失败: {str(e)}')
            messages.error(request, f'重置失败：{str(e)}')

        return HttpResponseRedirect(
            reverse(
                'admin:%s_%s_changelist' % (
                    self.model._meta.app_label,
                    self.model._meta.model_name
                )
            )
        )
    def basic_stats_view(self, request, exam_id):
        """基础统计视图"""
        try:

            exam = BaseExamConfig.objects.get(exam_id=exam_id)
            configs = ExamLevelAnalysisConfig.objects.filter(
                exam_id=exam_id,
                is_active=True
            )

            context = {
                'title': f'{exam.exam_name} - 基础统计',
                'opts': self.model._meta,
                'app_label': self.model._meta.app_label,
                'exam': exam,
                'configs': configs,
                'has_change_permission': self.has_change_permission(request),
                'is_popup': False,
                'media': self.media,
            }

            return TemplateResponse(
                request,
                'admin/exam_level/basic_stats.html',
                context
            )

        except Exception as e:
            messages.error(request, str(e))
            return HttpResponseRedirect('../')

