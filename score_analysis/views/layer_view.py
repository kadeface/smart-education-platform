# views/layer_view.py
from django.views import View
from django.shortcuts import render

from score_analysis.models import BaseExamConfig
from score_analysis.models.region import LayerAnalysis
from score_analysis.services import LayerAnalysisService
from score_analysis.services.region.layer_view import LayerViewService
import logging
logger = logging.getLogger(__name__)
class LayerView(View):
    """层次分析视图"""

    # views/layer_view.py
    def get(self, request, module_type, exam_id):
        """获取层次分析数据。

        Args:
            request: HTTP请求对象
            module_type: 模块类型
            exam_id: 考试ID

        Returns:
            HttpResponse: 渲染后的页面
        """
        try:
            # 1. 先获取考试配置，判断是否分科
            exam_config = BaseExamConfig.objects.get(exam_id=exam_id)
            is_divided = exam_config.is_divided_exam

            # 2. 根据是否分科决定 select_type
            select_type = request.GET.get('select_type', '理科') if is_divided else '未确定'
            selected_districts = request.GET.getlist('districts', [])

            logger.info(f"""
            开始获取数据:
            - exam_id: {exam_id}
            - is_divided: {is_divided}
            - select_type: {select_type}
            """)

            # 3. 先检查是否存在分析数据，不存在则生成
            if not LayerAnalysis.objects.filter(exam_id=exam_id, select_type=select_type).exists():
                logger.info(f"未找到考试 {exam_id} 的分层分析数据，开始生成...")
                analysis_service = LayerAnalysisService()
                analysis_service.generate_layer_analysis(exam_id)

            # 4. 获取分析数据
            service = LayerViewService()
            exam_info = service.get_exam_info(exam_id)
            layer_types = service.get_layer_types(exam_id, select_type)
            district_analysis = service.get_district_analysis(exam_id, select_type)
            all_districts = service.get_all_districts(exam_id)

            # 如果没有选择区县，默认选择所有区县
            if not selected_districts:
                selected_districts = list(all_districts)

            # 获取学校分析数据
            school_analysis = service.get_school_analysis(exam_id, select_type, selected_districts)

            # 只有分科考试才需要切换URL
            science_url = ""
            liberal_url = ""
            if is_divided:
                science_url = "?select_type=理科"
                liberal_url = "?select_type=文科"

            context = {
                'exam_info': exam_info,
                'is_divided': is_divided,
                'select_type': select_type,
                'layer_types': layer_types,
                'district_analysis': district_analysis,
                'all_districts': all_districts,
                'selected_districts': selected_districts,
                'school_analysis': school_analysis,
                'science_url': science_url,
                'liberal_url': liberal_url
            }

            return render(request, 'score_analysis/region/layer_analysis.html', context)

        except Exception as e:
            logger.error(f"处理层次分析视图时发生错误: {str(e)}")
            return render(request, 'score_analysis/error.html', {'error': '处理数据时发生错误'})