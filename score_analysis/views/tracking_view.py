# views/trackingview.py

from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from ..models import ExamScore, Student, Class, TrackingRecord


class TrackingBaseView(View):
    """发展跟踪基础视图类"""

    def get_exam_info(self, exam_id):
        """获取考试基本信息"""
        try:
            exam = ExamScore.objects.filter(exam_id=exam_id).first()
            return {
                'exam_id': exam_id,
                'name': exam.exam_name,
                'exam_date': exam.exam_date,
                'grade': exam.grade,
                'student_count': ExamScore.objects.filter(exam_id=exam_id).count()
            }
        except Exception as e:
            return {}

    def get_class_list(self, school_level, exam_id):
        """获取班级列表"""
        return Class.objects.filter(
            school_level=school_level,
            examstudent__exam_id=exam_id
        ).distinct().values('id', 'name')


class ScoreRankingView(TrackingBaseView):
    """成绩排名查询视图"""
    template_name = 'tracking/score_ranking.html'

    def get(self, request, school_level, exam_id):
        """显示成绩排名查询页面"""
        context = {
            'school_level': school_level,
            'exam_id': exam_id,
            'exam_info': self.get_exam_info(exam_id),
            'classes': self.get_class_list(school_level, exam_id),
            'subjects': self.get_subject_list(school_level)
        }
        return render(request, self.template_name, context)

    def get_subject_list(self, school_level):
        """获取科目列表"""
        subjects = {
            'H': ['chinese', 'math', 'english', 'physics', 'chemistry',
                  'biology', 'politics', 'history', 'geography'],
            'M': ['chinese', 'math', 'english', 'physics', 'chemistry',
                  'biology', 'politics', 'history', 'geography'],
            'P': ['chinese', 'math', 'english']
        }
        return subjects.get(school_level, [])


class ScoreTrendView(TrackingBaseView):
    """成绩变化趋势视图"""
    template_name = 'tracking/score_trends.html'

    def get(self, request, school_level, exam_id):
        """显示成绩变化趋势页面"""
        context = {
            'school_level': school_level,
            'exam_id': exam_id,
            'exam_info': self.get_exam_info(exam_id),
            'exam_list': self.get_exam_history(school_level, exam_id)
        }
        return render(request, self.template_name, context)

    def get_exam_history(self, school_level, exam_id):
        """获取历史考试列表"""
        current_exam = ExamScore.objects.filter(exam_id=exam_id).first()
        if current_exam:
            return ExamScore.objects.filter(
                grade=current_exam.grade,
                school_level=school_level
            ).values('exam_id', 'exam_name', 'exam_date').distinct()
        return []


class StudentGroupView(TrackingBaseView):
    """学生群体分析视图"""
    template_name = 'tracking/student_groups.html'

    def get(self, request, school_level, exam_id):
        """显示学生群体分析页面"""
        context = {
            'school_level': school_level,
            'exam_id': exam_id,
            'exam_info': self.get_exam_info(exam_id),
            'group_types': self.get_group_types()
        }
        return render(request, self.template_name, context)

    def get_group_types(self):
        """获取群体类型"""
        return [
            {'code': 'top', 'name': '尖子群'},
            {'code': 'special', 'name': '特控群'},
            {'code': 'undergraduate', 'name': '本科群'},
            {'code': 'special_border', 'name': '特控临界'},
            {'code': 'undergraduate_border', 'name': '本科临界'}
        ]


class WarningPredictionView(TrackingBaseView):
    """预警与预测视图"""
    template_name = 'tracking/warnings.html'

    def get(self, request, school_level, exam_id):
        """显示预警与预测页面"""
        context = {
            'school_level': school_level,
            'exam_id': exam_id,
            'exam_info': self.get_exam_info(exam_id),
            'warning_types': self.get_warning_types()
        }
        return render(request, self.template_name, context)

    def get_warning_types(self):
        """获取预警类型"""
        return [
            {'code': 'score_drop', 'name': '成绩下滑'},
            {'code': 'subject_imbalance', 'name': '科目失衡'},
            {'code': 'border_state', 'name': '临界状态'},
            {'code': 'abnormal', 'name': '异常表现'}
        ]


# API视图
class StudentScoreAPI(TrackingBaseView):
    """学生成绩数据API"""

    def get(self, request):
        """获取学生成绩数据"""
        student_id = request.GET.get('student_id')
        exam_id = request.GET.get('exam_id')

        scores = self.get_student_scores(student_id, exam_id)
        return JsonResponse({'scores': scores})

    def get_student_scores(self, student_id, exam_id):
        """获取学生成绩详情"""
        tracking_record = TrackingRecord.objects.filter(
            student_id=student_id,
            exam_id=exam_id
        ).first()

        if tracking_record:
            return {
                'subject_scores': tracking_record.subject_scores,
                'subject_ranks': tracking_record.subject_ranks,
                'subject_t_scores': tracking_record.subject_t_scores
            }
        return {}


class StudentListAPI(TrackingBaseView):
    """学生列表API"""

    def get(self, request):
        """获取班级学生列表"""
        class_id = request.GET.get('class_id')
        exam_id = request.GET.get('exam_id')

        students = Student.objects.filter(
            class_id=class_id,
            examstudent__exam_id=exam_id
        ).values('id', 'name')

        return JsonResponse({'students': list(students)})


class ScoreTrendAPI(TrackingBaseView):
    """成绩趋势数据API"""

    def get(self, request):
        """获取成绩趋势数据"""
        student_id = request.GET.get('student_id')
        subject = request.GET.get('subject')

        trend_data = self.get_score_trend(student_id, subject)
        return JsonResponse({'trend_data': trend_data})

    def get_score_trend(self, student_id, subject):
        """获取成绩趋势数据"""
        records = TrackingRecord.objects.filter(
            student_id=student_id
        ).order_by('exam_id')

        return [{
            'exam_id': record.exam_id,
            'score': record.subject_scores.get(subject),
            'rank': record.subject_ranks.get(subject),
            't_score': record.subject_t_scores.get(subject)
        } for record in records]


class GroupAnalysisAPI(TrackingBaseView):
    """群体分析数据API"""

    def get(self, request):
        """获取群体分析数据"""
        exam_id = request.GET.get('exam_id')
        group_type = request.GET.get('group_type')

        group_data = self.get_group_analysis(exam_id, group_type)
        return JsonResponse({'group_data': group_data})

    def get_group_analysis(self, exam_id, group_type):
        """获取群体分析数据"""
        # 根据不同群体类型返回相应的分析数据
        # 这里需要根据具体的业务逻辑实现
        return {}