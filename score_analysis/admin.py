#score_analysis/score_analysis.py:
from django.urls import path ,reverse
from django.template.response import TemplateResponse  # 添加这行导入
from django.db import connection
from django import forms
from django.shortcuts import render
from django.db.models import Q
from django.utils.safestring import mark_safe
from .models.statistics import ExamScoreLines,ScoreRankings, StatisticsExamIndicators
from .models.base import BaseExamConfig
from django.contrib.admin import SimpleListFilter
from django.contrib import admin,messages
from django.shortcuts import redirect
from .models.base import BaseExamConfig,BaseSubjectConfig
from .services.ranking_service import RankingService
from .models.source import ScoreStudentBasic
from .services.statistics import BaseStatisticsService
from django.db.models import Subquery, OuterRef
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
        existing_stats = StatisticsExamIndicators.objects.filter(
            exam_id__in=exams_with_scores,
            select_type='理科',
            level_type='city'
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
                        level_type='city'
                    )
                )
            if stats_to_create:
                StatisticsExamIndicators.objects.bulk_create(stats_to_create)
                # 重新查询，包含考试名称
                return StatisticsExamIndicators.objects.filter(
                    exam_id__in=exams_with_scores,
                    select_type='理科',
                    level_type='city'
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
        if obj.student_count:
            return mark_safe('<span style="color: green;">✓</span>')
        return mark_safe('<span style="color: red;">✗</span>')

    has_statistics.short_description = '已生成统计'


    def get_action_button(self, obj):
        """获取操作按钮"""
        button_text = "重新统计" if obj.student_count else "生成统计"

        generate_url = reverse(
            'admin:score_analysis_statisticsexamindicators_generate',
            args=[obj.exam_id]
        )

        buttons = [
            f'<a class="button" style="background-color: #79aec8; padding: 5px 10px; '
            f'color: white; text-decoration: none; border-radius: 4px; margin-right: 5px;" '
            f'href="{generate_url}">{button_text}</a>'
        ]

        if obj.student_count:
            view_url = reverse(
                'score_analysis:score_analysis_statisticsexamindicators_view',
                args=[obj.exam_id]
            )
            buttons.append(
                f'<a class="button" style="background-color: #417690; padding: 5px 10px; '
                f'color: white; text-decoration: none; border-radius: 4px;" '
                f'href="{view_url}">查看结果</a>'
            )

        return mark_safe(''.join(buttons))

    def generate_statistics(self, request, exam_id):
        """生成统计数据"""
        try:
            print(f"开始生成统计数据: exam_id={exam_id}")  # 调试日志
            service = BaseStatisticsService()

            # 生成理科和文科的统计
            service.generate_all_statistics(exam_id, '理科', 'city')
            service.generate_all_statistics(exam_id, '文科', 'city')

            messages.success(request, f'考试 {exam_id} 的统计数据已生成')

            # 打印重定向URL
            redirect_url = f'../view-statistics/{exam_id}/'
            print(f"重定向到: {redirect_url}")  # 调试日志

            return redirect(redirect_url)

        except Exception as e:
            print(f"生成统计失败: {str(e)}")  # 调试日志
            messages.error(request, f'考试 {exam_id} 统计数据生成失败: {str(e)}')
            return redirect('../')

    def get_urls(self):
        """添加自定义URL"""
        urls = super().get_urls()
        custom_urls = [
            path('generate-statistics/<str:exam_id>/',
                 self.admin_site.admin_view(self.generate_statistics),
                 name='score_analysis_statisticsexamindicators_generate'),
            path('view-statistics/<str:exam_id>/',
                 self.admin_site.admin_view(self.view_statistics),
                 name='score_analysis_statisticsexamindicators_view'),
        ]
        return custom_urls + urls

    def view_statistics(self, request, exam_id):
        """查看统计结果页面"""
        try:
            # 获取考试基本信息
            exam = BaseExamConfig.objects.filter(exam_id=exam_id).first()

            # 获取分数线数据
            score_lines = ExamScoreLines.objects.filter(exam_id=exam_id)
            score_lines_dict = {
                f"{line.select_type}_{line.line_type}": line.score
                for line in score_lines
            }

            # 获取理科统计数据
            science_stats = StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                select_type='理科',
                level_type='city'
            ).first()

            # 获取文科统计数据
            arts_stats = StatisticsExamIndicators.objects.filter(
                exam_id=exam_id,
                select_type='文科',
                level_type='city'
            ).first()

            # 准备理科数据
            science_data = self._prepare_subject_data(science_stats, score_lines_dict, '理科')

            # 准备文科数据
            arts_data = self._prepare_subject_data(arts_stats, score_lines_dict, '文科')

            # 准备模板数据
            context = {
                'title': f'{exam.exam_name if exam else exam_id} - 统计结果',
                'exam_id': exam_id,
                'exam_name': exam.exam_name if exam else exam_id,
                'science_data': science_data,
                'arts_data': arts_data,
                **self.admin_site.each_context(request),
            }

            return render(
                request,
                'score_analysis/score_analysis/statisticsexamindicators/stats_content.html',
                context
            )

        except Exception as e:
            messages.error(request, f'获取统计数据失败: {str(e)}')
            return redirect('..')


    def _prepare_subject_data(self, stats, score_lines, select_type):
        """准备学科统计数据"""
        if not stats:
            return {}

        # 1. 获取最高分学校
        top_school = "暂无数据"
        if stats.school_distribution:
            top_scores = sorted(
                [(school, data.get('max_score', 0))
                 for school, data in stats.school_distribution.items()],
                key=lambda x: x[1],
                reverse=True
            )
            if top_scores:
                top_school = top_scores[0][0]

        # 2. 准备基础数据
        data = {
            # 基本信息
            'school_count': len(stats.school_distribution or {}),
            'student_count': stats.student_count,
            'mean_score': stats.mean_score,
            'max_score': stats.max_score,
            'top_school': top_school,

            # 分数线和上线数据
            'qb_line': score_lines.get(f'{select_type}_qb', 0),
            'qb_count': stats.threshold_stats.get('qb', {}).get('count', 0),
            'qb_rate': stats.threshold_stats.get('qb', {}).get('rate', 0),

            '985_line': score_lines.get(f'{select_type}_985', 0),
            '985_count': stats.threshold_stats.get('985', {}).get('count', 0),
            '985_rate': stats.threshold_stats.get('985', {}).get('rate', 0),

            '211_line': score_lines.get(f'{select_type}_211', 0),
            '211_count': stats.threshold_stats.get('211', {}).get('count', 0),
            '211_rate': stats.threshold_stats.get('211', {}).get('rate', 0),

            'tk_line': score_lines.get(f'{select_type}_tk', 0),
            'tk_count': stats.threshold_stats.get('tk', {}).get('count', 0),
            'tk_rate': stats.threshold_stats.get('tk', {}).get('rate', 0),

            'bk_line': score_lines.get(f'{select_type}_bk', 0),
            'bk_count': stats.threshold_stats.get('bk', {}).get('count', 0),
            'bk_rate': stats.threshold_stats.get('bk', {}).get('rate', 0),

            'zk_line': score_lines.get(f'{select_type}_zk', 0),
            'zk_count': stats.threshold_stats.get('zk', {}).get('count', 0),
            'zk_rate': stats.threshold_stats.get('zk', {}).get('rate', 0),

        }
        # 2. 处理学校分布数据
        school_stats = []
        if stats.school_distribution:
            for school_name, school_data in stats.school_distribution.items():
                school_info = {
                    'name': school_name,
                    'student_count': school_data.get('student_count', 0),
                    'max_score': school_data.get('max_score', 0),
                    'min_score': school_data.get('min_score', 0),
                    'mean_score': school_data.get('mean_score', 0),
                    'mean_rank': school_data.get('mean_rank', 0),

                    # 各分数线上线数据
                    'qb_count': school_data.get('threshold_stats', {}).get('qb', {}).get('count', 0),
                    'qb_rate': school_data.get('threshold_stats', {}).get('qb', {}).get('rate', 0),

                    '985_count': school_data.get('threshold_stats', {}).get('985', {}).get('count', 0),
                    '985_rate': school_data.get('threshold_stats', {}).get('985', {}).get('rate', 0),

                    '211_count': school_data.get('threshold_stats', {}).get('211', {}).get('count', 0),
                    '211_rate': school_data.get('threshold_stats', {}).get('211', {}).get('rate', 0),

                    'tk_count': school_data.get('threshold_stats', {}).get('tk', {}).get('count', 0),
                    'tk_rate': school_data.get('threshold_stats', {}).get('tk', {}).get('rate', 0),

                    'bk_count': school_data.get('threshold_stats', {}).get('bk', {}).get('count', 0),
                    'bk_rate': school_data.get('threshold_stats', {}).get('bk', {}).get('rate', 0),

                    'zk_count': school_data.get('threshold_stats', {}).get('zk', {}).get('count', 0),
                    'zk_rate': school_data.get('threshold_stats', {}).get('zk', {}).get('rate', 0),
                }
                school_stats.append(school_info)

        # 按平均分排序
        school_stats.sort(key=lambda x: x['mean_score'], reverse=True)

        # 添加到返回数据中
        data['school_stats'] = school_stats

        # 3. 处理科目统计数据
        subject_stats = {}
        if stats.subject_stats:
            # 理科科目
            if select_type == '理科':
                subjects = ['total', 'chinese', 'math', 'english', 'physics', 'chemistry', 'biology']
            # 文科科目
            else:
                subjects = ['total', 'chinese', 'math', 'english', 'politics', 'history', 'geography']

            for subject in subjects:
                subject_data = stats.subject_stats.get(subject, {})
                subject_stats[subject] = {
                    'mean': subject_data.get('mean', 0),  # 均分
                    'max': subject_data.get('max', 0),  # 最高分
                    'min': subject_data.get('min', 0),  # 最低分
                    'median': subject_data.get('median', 0),  # 中位数
                    'q80': subject_data.get('q80', 0),  # 80分位
                    'q20': subject_data.get('q20', 0),  # 20分位
                    'q10': subject_data.get('q10', 0),  # 10分位
                }

        # 添加到返回数据中
        data['subject_stats'] = subject_stats

        # 为了方便模板使用，添加直接访问的字段
        for subject, stats in subject_stats.items():
            for stat_type, value in stats.items():
                # 例如: total_mean, chinese_max, math_q80 等
                data[f'{subject}_{stat_type}'] = value

        # 4. 处理排名分布数据
        rank_stats = {}
        if stats.rank_distribution:
            # 4.1 处理各分数段的最低分
            rank_thresholds = {
                'top10': stats.rank_distribution.get('top10', {}).get('min_score', 0),
                'top20': stats.rank_distribution.get('top20', {}).get('min_score', 0),
                'top50': stats.rank_distribution.get('top50', {}).get('min_score', 0),
                'top100': stats.rank_distribution.get('top100', {}).get('min_score', 0),
                'top200': stats.rank_distribution.get('top200', {}).get('min_score', 0),
                'top500': stats.rank_distribution.get('top500', {}).get('min_score', 0),
                'top1250': stats.rank_distribution.get('top1250', {}).get('min_score', 0),
            }

            # 4.2 处理学校的排名分布
            school_rank_stats = {}
            for school_name, school_data in stats.school_distribution.items():
                school_ranks = school_data.get('rank_stats', {})
                school_rank_stats[school_name] = {
                    'top10': school_ranks.get('top10', 0),
                    'top20': school_ranks.get('top20', 0),
                    'top50': school_ranks.get('top50', 0),
                    'top100': school_ranks.get('top100', 0),
                    'top200': school_ranks.get('top200', 0),
                    'top500': school_ranks.get('top500', 0),
                    'top1250': school_ranks.get('top1250', 0),
                }

            # 4.3 计算总体排名分布
            total_rank_stats = {
                'top10': sum(school.get('top10', 0) for school in school_rank_stats.values()),
                'top20': sum(school.get('top20', 0) for school in school_rank_stats.values()),
                'top50': sum(school.get('top50', 0) for school in school_rank_stats.values()),
                'top100': sum(school.get('top100', 0) for school in school_rank_stats.values()),
                'top200': sum(school.get('top200', 0) for school in school_rank_stats.values()),
                'top500': sum(school.get('top500', 0) for school in school_rank_stats.values()),
            }

            rank_stats = {
                'thresholds': rank_thresholds,
                'total': total_rank_stats,
                'schools': school_rank_stats
            }

        # 添加到返回数据中
        data['rank_stats'] = rank_stats

        # 为了方便模板使用，添加直接访问的字段
        for rank, score in rank_stats.get('thresholds', {}).items():
            data[f'{rank}_min'] = score
        for rank, count in rank_stats.get('total', {}).items():
            data[f'{rank}_total'] = count

        # 5. 处理平均分数据
        avg_stats = {
            'total': {
                'name': '总体',
                'scores': {}
            }
        }

        # 5.1 确定科目列表
        if select_type == '理科':
            subjects = [
                ('total', '总分'),
                ('chinese', '语文'),
                ('math', '数学'),
                ('english', '英语'),
                ('physics', '物理'),
                ('chemistry', '化学'),
                ('biology', '生物')
            ]
        else:  # 文科
            subjects = [
                ('total', '总分'),
                ('chinese', '语文'),
                ('math', '数学'),
                ('english', '英语'),
                ('politics', '政治'),
                ('history', '历史'),
                ('geography', '地理')
            ]

        # 5.2 处理总体平均分
        for subject_code, _ in subjects:
            subject_stats = stats.subject_stats.get(subject_code, {})
            avg_stats['total']['scores'][subject_code] = {
                'avg': subject_stats.get('mean', 0),
                'rank': 0  # 总体不需要排名
            }

        # 5.3 处理各学校平均分
        if stats.school_distribution:
            school_avgs = []
            for school_name, school_data in stats.school_distribution.items():
                school_subjects = school_data.get('subject_stats', {})
                school_info = {
                    'name': school_name,
                    'scores': {}
                }

                # 获取每个科目的均分
                for subject_code, _ in subjects:
                    subject_data = school_subjects.get(subject_code, {})
                    school_info['scores'][subject_code] = {
                        'avg': subject_data.get('mean', 0),
                        'rank': subject_data.get('rank', 0)
                    }

                school_avgs.append(school_info)

            # 按总分均分排序
            school_avgs.sort(
                key=lambda x: x['scores']['total']['avg'],
                reverse=True
            )

            # 添加到平均分统计中
            for school in school_avgs:
                avg_stats[school['name']] = {
                    'name': school['name'],
                    'scores': school['scores']
                }

        # 添加到返回数据中
        data['avg_stats'] = avg_stats

        # 为了方便模板使用，添加直接访问字段
        for subject_code, _ in subjects:
            data[f'{subject_code}_avg'] = avg_stats['total']['scores'][subject_code]['avg']

        return data