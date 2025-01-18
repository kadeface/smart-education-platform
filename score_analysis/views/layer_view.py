# views/layer_view.py
from django.views import View
from django.shortcuts import render

from score_analysis.models import BaseExamConfig
from score_analysis.services.region.layer_view import LayerViewService
import logging
logger = logging.getLogger(__name__)
class LayerView(View):
    """层次分析视图"""

    # views/layer_view.py
    def get(self, request, module_type, exam_id):
        """
        @param module_type: 模块类型（这里不使用）
        @param exam_id: 考试ID
        """
        try:
            service = LayerViewService()
            select_type = request.GET.get('select_type', '文科')  # 默认理科
            selected_districts = request.GET.getlist('districts', [])
            logger.info(f"开始获取数据 - exam_id: {exam_id}, select_type: {select_type}")
            # 获取考试配置
            exam_config = BaseExamConfig.objects.get(exam_id=exam_id)
            is_divided = exam_config.is_divided_exam

            # 获取基础数据
            exam_info = service.get_exam_info(exam_id)
            logger.info(f"exam_info: {exam_info}")  # 添加日志
            layer_types = service.get_layer_types(exam_id, select_type)
            logger.info(f"layer_types: {layer_types}")  # 添加日志
            district_analysis = service.get_district_analysis(exam_id, select_type)
            all_districts = service.get_all_districts(exam_id)

            # 如果没有选择区县，默认选择所有区县
            if not selected_districts:
                selected_districts = list(all_districts)

            # 获取学校分析数据
            school_analysis = service.get_school_analysis(exam_id, select_type, selected_districts)

            context = {
                'exam_info': exam_info,
                'is_divided': is_divided,
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
        except Exception as e:
            logger.error(f"处理层次分析视图时发生错误: {str(e)}")
            return render(request, 'score_analysis/error.html', {'error': '处理数据时发生错误'})


