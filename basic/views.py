# basic/views.py
from django.http import JsonResponse
from django.views import View
from .models import StudentIDMapping


class StudentMappingView(View):
    def get(self, request):
        """获取学生ID映射信息"""
        student_registration = request.GET.get('registration')
        try:
            student = StudentIDMapping.objects.get(
                student_registration=student_registration
            )
            return JsonResponse({
                'code': 0,
                'data': {
                    'student_name': student.student_name,
                    'current_level': student.current_level,
                    'ids': {
                        'primary': student.primary_id,
                        'middle': student.middle_id,
                        'high': student.high_id
                    }
                }
            })
        except StudentIDMapping.DoesNotExist:
            return JsonResponse({
                'code': 404,
                'message': '学生不存在'
            }, status=404)


from django.shortcuts import render

# Create your views here.
