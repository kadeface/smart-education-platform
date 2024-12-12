
# score_analysis/views/api.py
from django.http import JsonResponse
from django.views import View
from ..models.statistics import StatisticsExamIndicators, ExamScoreLines


class StatisticsDataAPIView(View):
    def get(self, request):
        try:
            exam_id = request.GET.get('exam_id')
            if not exam_id:
                return JsonResponse({'error': '缺少考试ID'}, status=400)

            # 先写一个简单的返回，确保路由正常
            return JsonResponse({
                'status': 'ok',
                'exam_id': exam_id
            })

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


