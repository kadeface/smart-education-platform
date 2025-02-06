# score_analysis/tasks.py
from celery import shared_task
from .services.value_added_service import StudentGrowthService
from django.core.cache import cache


@shared_task(bind=True)
def generate_growth_analysis_task(self, school_level, config):
    """
    异步生成增长分析

    Args:
        school_level: 学段代码
        config: 分析配置
    """
    try:
        # 更新任务状态
        self.update_state(
            state='PROGRESS',
            meta={'progress': 0, 'message': '正在初始化...'}
        )

        # 创建服务实例
        service = StudentGrowthService(
            subject_config=config['subject_config'],
            subject_full_scores=config['subject_full_scores'],
            exam_types=config['exam_types']
        )

        # 获取考试ID列表
        exam_ids = service.get_recent_exams(school_level)

        # 更新进度
        self.update_state(
            state='PROGRESS',
            meta={'progress': 20, 'message': '正在计算学生成长曲线...'}
        )

        # 计算增长分析
        growth_data = service.calculate_student_growth(exam_ids)

        self.update_state(
            state='PROGRESS',
            meta={'progress': 60, 'message': '正在生成分析报告...'}
        )

        # 分析增长模式
        growth_analysis = service.analyze_growth_patterns(growth_data)

        # 保存结果
        cache_key = f'growth_analysis_{school_level}'
        cache.set(cache_key, {
            'data': growth_data.to_dict('records'),
            'analysis': growth_analysis
        }, timeout=86400)  # 24小时过期

        return {
            'status': 'success',
            'message': '分析完成'
        }

    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }