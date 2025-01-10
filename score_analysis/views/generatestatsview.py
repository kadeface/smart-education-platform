from django.views.generic import TemplateView
from django.shortcuts import render

from score_analysis.models.statistics import ExamLevelStatistics


class GenerateStatsView(TemplateView):
    template_name = 'score_analysis/statistics/generate_stats.html'



    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 从 kwargs 获取 exam_id，而不是从 request.GET
        exam_id = kwargs.get('exam_id')

        if not exam_id:
            return context

        # 获取理科统计数据
        science_stats = ExamLevelStatistics.objects.filter(
            exam_id=exam_id,
            select_type='理科',
            level_type='city'
        ).first()
        print("Debug - exam_id:", exam_id)  # 调试信息
        # 获取理科统计数据
        science_stats = ExamLevelStatistics.objects.filter(
            exam_id=exam_id,
            select_type='理科',
            level_type='city'
        ).first()
        print("Debug - science_stats:", science_stats)  # 调试信息
        # 获取文科统计数据
        arts_stats = ExamLevelStatistics.objects.filter(
            exam_id=exam_id,
            select_type='文科',
            level_type='city'
        ).first()
        print("Debug - arts_stats:", arts_stats)  # 调试信息
        # 准备理科数据
        # 准备理科数据
        if science_stats:
            context.update({
                'science_school_count': getattr(science_stats, 'school_count', '-'),
                'science_student_count': getattr(science_stats, 'student_count', '-'),
                'science_mean_score': round(science_stats.mean_score, 2) if hasattr(science_stats,
                                                                                    'mean_score') else '-',
                'science_max_score': getattr(science_stats, 'max_score', '-'),
                'science_min_score': getattr(science_stats, 'min_score', '-'),

                # 分数线数据
                'science_qb_line': getattr(science_stats, 'qb_line', '-'),
                'science_qb_count': getattr(science_stats, 'qb_count', '-'),
                'science_qb_rate': getattr(science_stats, 'qb_rate', '-'),

                'science_985_line': getattr(science_stats, '985_line', '-'),
                'science_985_count': getattr(science_stats, '985_count', '-'),
                'science_985_rate': getattr(science_stats, '985_rate', '-'),

                'science_211_line': getattr(science_stats, '211_line', '-'),
                'science_211_count': getattr(science_stats, '211_count', '-'),
                'science_211_rate': getattr(science_stats, '211_rate', '-'),

                'science_tk_line': getattr(science_stats, 'tk_line', '-'),
                'science_tk_count': getattr(science_stats, 'tk_count', '-'),
                'science_tk_rate': getattr(science_stats, 'tk_rate', '-'),

                'science_bk_line': getattr(science_stats, 'bk_line', '-'),
                'science_bk_count': getattr(science_stats, 'bk_count', '-'),
                'science_bk_rate': getattr(science_stats, 'bk_rate', '-'),

                'science_zk_line': getattr(science_stats, 'zk_line', '-'),
                'science_zk_count': getattr(science_stats, 'zk_count', '-'),
                'science_zk_rate': getattr(science_stats, 'zk_rate', '-'),
            })

        # 准备文科数据
        if arts_stats:
            context.update({
                'arts_school_count': getattr(arts_stats, 'school_count', '-'),
                'arts_student_count': getattr(arts_stats, 'student_count', '-'),
                'arts_mean_score': round(arts_stats.mean_score, 2) if hasattr(arts_stats, 'mean_score') else '-',
                'arts_max_score': getattr(arts_stats, 'max_score', '-'),
                'arts_min_score': getattr(arts_stats, 'min_score', '-'),

                # 分数线数据
                'arts_qb_line': getattr(arts_stats, 'qb_line', '-'),
                'arts_qb_count': getattr(arts_stats, 'qb_count', '-'),
                'arts_qb_rate': getattr(arts_stats, 'qb_rate', '-'),

                'arts_985_line': getattr(arts_stats, '985_line', '-'),
                'arts_985_count': getattr(arts_stats, '985_count', '-'),
                'arts_985_rate': getattr(arts_stats, '985_rate', '-'),

                'arts_211_line': getattr(arts_stats, '211_line', '-'),
                'arts_211_count': getattr(arts_stats, '211_count', '-'),
                'arts_211_rate': getattr(arts_stats, '211_rate', '-'),

                'arts_tk_line': getattr(arts_stats, 'tk_line', '-'),
                'arts_tk_count': getattr(arts_stats, 'tk_count', '-'),
                'arts_tk_rate': getattr(arts_stats, 'tk_rate', '-'),

                'arts_bk_line': getattr(arts_stats, 'bk_line', '-'),
                'arts_bk_count': getattr(arts_stats, 'bk_count', '-'),
                'arts_bk_rate': getattr(arts_stats, 'bk_rate', '-'),

                'arts_zk_line': getattr(arts_stats, 'zk_line', '-'),
                'arts_zk_count': getattr(arts_stats, 'zk_count', '-'),
                'arts_zk_rate': getattr(arts_stats, 'zk_rate', '-'),
            })

        return context
