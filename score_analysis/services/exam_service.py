from django.db import transaction
from ..models.statistics import StatisticsExamIndicators
from ..models.source import ScoreStudentBasic
from .exam_statistics import ExamStatisticsService


class ExamService:
    @staticmethod
    def get_exam_statistics(exam_id):
        """获取考试统计数据"""
        try:
            # 初始化统计服务
            stats_service = ExamStatisticsService()

            # 获取考试的所有统计数据
            exam_stats = stats_service.process_exam_statistics(exam_id)

            # 获取文理科类型
            stream_types = ScoreStudentBasic.objects.filter(
                exam_id=exam_id
            ).values_list('select_type', flat=True).distinct()

            # 初始化返回数据结构
            basic_stats = {
                'student_count': 0,
                'mean': 0.0,
                'std_dev': 0.0,
                'max_score': 0.0,
                'min_score': 0.0,
                'pass_rate': 0.0,
                'excellent_rate': 0.0,
                'level_distribution': [],
                'distribution_data': [],
                'subject_stats': {}
            }

            # 合并所有文理科的统计数据
            for stream_type in stream_types:
                # 获取市级统计数据（可以根据需要改为区级或校级）
                stats_key = f"{stream_type}_city"
                if stats_key in exam_stats:
                    total_stats = exam_stats[stats_key]['total']

                    # 更新基础统计数据
                    basic_stats['mean'] = round(float(total_stats.mean_score), 1)
                    basic_stats['std_dev'] = round(float(total_stats.std_dev), 1)

                    # 从threshold_stats中获取分数线信息
                    if total_stats.threshold_stats:
                        thresholds = total_stats.threshold_stats
                        basic_stats['max_score'] = float(thresholds.get('max_score', 0))
                        basic_stats['min_score'] = float(thresholds.get('min_score', 0))

                    # 获取学科统计
                    subject_stats = exam_stats[stats_key]['subjects']
                    for subject_id, subject_stat in subject_stats.items():
                        if subject_id not in basic_stats['subject_stats']:
                            basic_stats['subject_stats'][subject_id] = {
                                'mean': round(float(subject_stat.mean_score), 1),
                                'std_dev': round(float(subject_stat.std_dev), 1),
                                'pass_rate': float(subject_stat.pass_rate),
                                'excellent_rate': float(subject_stat.excellent_rate)
                            }

            # 计算等级分布
            level_ranges = [
                {'name': '优秀', 'min': 90, 'max': 100},
                {'name': '良好', 'min': 80, 'max': 89.9},
                {'name': '中等', 'min': 70, 'max': 79.9},
                {'name': '及格', 'min': 60, 'max': 69.9},
                {'name': '不及格', 'min': 0, 'max': 59.9}
            ]

            for level in level_ranges:
                count = ScoreStudentBasic.objects.filter(
                    exam_id=exam_id,
                    total_score__gte=level['min'],
                    total_score__lte=level['max']
                ).count()

                total_students = ScoreStudentBasic.objects.filter(
                    exam_id=exam_id
                ).count()

                percentage = round((count / total_students * 100), 1) if total_students > 0 else 0

                basic_stats['level_distribution'].append({
                    'name': level['name'],
                    'range': f"{level['min']}-{level['max']}",
                    'count': count,
                    'percentage': percentage
                })

            # 计算分数分布（每10分一个区间）
            for i in range(0, 101, 10):
                count = ScoreStudentBasic.objects.filter(
                    exam_id=exam_id,
                    total_score__gte=i,
                    total_score__lt=i + 10
                ).count()

                basic_stats['distribution_data'].append({
                    'range': f"{i}-{i + 9.9}",
                    'count': count
                })

            # 更新学生总数
            basic_stats['student_count'] = ScoreStudentBasic.objects.filter(
                exam_id=exam_id
            ).count()

            return {
                'exam': exam_id,  # 或者获取考试详细信息
                'basic_stats': basic_stats,
                'success': True
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'获取统计数据失败：{str(e)}'
            }