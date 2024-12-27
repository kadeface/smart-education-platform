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
        print(f"\n{'=' * 50}")
        print(f"开始处理请求：")
        print(f"exam_id: {exam_id}")
        print(f"GET参数: {dict(request.GET)}")

        try:
            # 获取请求参数
            select_type = request.GET.get('select_type', '理科')
            selected_districts = request.GET.getlist('districts')
            print(f"\n获取参数:")
            print(f"select_type: {select_type}")
            print(f"selected_districts: {selected_districts}")

            # 使用服务类
            service = LayerViewService()

            # 获取考试信息
            print("\n获取考试信息...")
            exam_info = service.get_exam_info(exam_id)
            print(f"exam_info: {exam_info}")

            # 获取区县分析
            print("\n获取区县分析...")
            district_analysis = service.get_district_analysis(exam_id, select_type)
            print(f"district_analysis keys: {district_analysis.keys()}")
            print(f"city_stats: {district_analysis.get('city_stats', {}).keys()}")
            print(f"district_stats: {district_analysis.get('district_stats', {}).keys()}")

            # 获取学校分析
            print("\n获取学校分析...")
            school_analysis = service.get_school_analysis(exam_id, select_type, selected_districts)
            print(f"school_analysis schools: {list(school_analysis.keys())}")

            # 获取区县列表
            print("\n获取区县列表...")
            all_districts = service.get_all_districts(exam_id)
            print(f"all_districts: {all_districts}")

            # 构建URL
            science_url = f"?select_type=理科"
            liberal_url = f"?select_type=文科"
            if selected_districts:
                for district in selected_districts:
                    science_url += f"&districts={district}"
                    liberal_url += f"&districts={district}"

            print("\n构建上下文...")
            context = {
                'exam_id': exam_id,
                'exam_info': exam_info,
                'select_type': select_type,
                'district_analysis': district_analysis,
                'school_analysis': school_analysis,
                'all_districts': all_districts,
                'selected_districts': selected_districts,
                'science_url': science_url,
                'liberal_url': liberal_url,
                'is_city_exam': 'CITY' in exam_id.upper()
            }
            print(f"context keys: {context.keys()}")

            print("\n开始渲染模板...")
            response = render(request, 'score_analysis/region/layer_analysis.html', context)
            print("渲染完成")
            print(f"{'=' * 50}\n")

            return response

        except Exception as e:
            print(f"\n发生错误:")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            logger.error(f"层次分析视图异常: {str(e)}", exc_info=True)
            return JsonResponse({
                'status': 'error',
                'message': '数据获取失败，请稍后重试'
            })


