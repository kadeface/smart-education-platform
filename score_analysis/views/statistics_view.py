from django.views.generic import View
from django.shortcuts import render, redirect
from django.contrib import messages
from score_analysis.services.statistics.statistics_service import StatisticsViewService


class StatisticsView(View):
    template_name = 'score_analysis/statistics/statistics_view.html'  # 新的模板路径

    def get(self, request, exam_id):
        """查看统计结果"""
        try:
            service = StatisticsViewService()

            # 获取考试层级信息
            level_type, districts = service._get_level_type(exam_id)

            # 获取理科和文科的统计数据
            science_stats = service._get_stats_by_type(exam_id, '理科')
            arts_stats = service._get_stats_by_type(exam_id, '文科')

            context = {
                'title': f'考试 {exam_id} 统计结果',
                'exam_id': exam_id,
                'level_type': level_type,
                'science_summary': service._process_summary_data(science_stats),
                'arts_summary': service._process_summary_data(arts_stats),
                'science_score_lines': service._score_line_distribution(science_stats),
                'arts_score_lines': service._score_line_distribution(arts_stats),
                'science_rankings': service._process_rank_distribution(science_stats),
                'arts_rankings': service._process_rank_distribution(arts_stats),
                'science_quartiles': service._process_quartile_analysis(science_stats, 'science'),
                'arts_quartiles': service._process_quartile_analysis(arts_stats, 'arts'),
                'science_school_means': service._process_school_subject_means(science_stats, 'science'),
                'arts_school_means': service._process_school_subject_means(arts_stats, 'arts'),
            }

            if level_type == '地市级' and districts:
                context['district_data'] = service._get_district_data(exam_id, districts)

            return render(request, self.template_name, context)

        except Exception as e:
            messages.error(request, f'获取统计数据失败: {str(e)}')
            return redirect('score_analysis:exam_list')  # 确保有这个URL名称