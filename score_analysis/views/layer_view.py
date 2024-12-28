# views/layer_view.py
from django.db.models import Count
from django.views import View
from django.shortcuts import render
from django.http import JsonResponse

from score_analysis.models.region import LayerAnalysis
from score_analysis.services.region.layer_view import LayerViewService
import logging

logger = logging.getLogger(__name__)


class LayerView(View):
    """层次分析视图"""

    def get(self, request, exam_id):
        service = LayerViewService()
        select_type = request.GET.get('select_type', '理科')
        selected_districts = request.GET.getlist('districts', [])

        # 获取基础数据
        exam_info = service.get_exam_info(exam_id)
        layer_types = service.get_layer_types(exam_id, select_type)
        district_analysis = service.get_district_analysis(exam_id, select_type)

        # 获取所有区县
        all_districts = service.get_all_districts(exam_id)

        # 如果没有选择区县，默认选择所有区县
        if not selected_districts:
            selected_districts = list(all_districts)

        # 获取学校分析数据
        school_analysis = service.get_school_analysis(exam_id, select_type, selected_districts)

        context = {
            'exam_info': exam_info,
            'select_type': select_type,
            'layer_types': layer_types,
            'district_analysis': district_analysis,
            'all_districts': all_districts,
            'selected_districts': selected_districts,
            'school_analysis': school_analysis,
            'science_url': f'?select_type=理科',
            'liberal_url': f'?select_type=文科'
        }

        return render(request, 'score_analysis/region/layer_analysis.html', context)


