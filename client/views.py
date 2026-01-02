from django.shortcuts import render,redirect
from django.db import connection
from django.urls import reverse
from datetime import datetime

def client_home(request):
    """首页视图"""
    return render(request, 'client/index.html')

def grade_select(request, module_type):
    """年级选择视图"""
    module_names = {
        'overview': '监测概况',
        'area': '区域评价',
        'value_added': '增值评价',
        'tracking': '跟踪监测'
    }
    # 如果是增值评价模块，使用学段而不是年级
    if module_type == 'value_added':
        school_levels = {
            '高中': 'H',
            '初中': 'M',
            '小学': 'P'
        }
        context = {
            'module_name': module_names.get(module_type, '未知模块'),
            'module_type': module_type,
            'is_value_added': True,  # 标记是增值评价模块
            'school_levels': school_levels,  # 学段数据
        }
        return render(request, 'client/school_level_select.html', context)
    # 计算当前年份和各年级对应的届别
    current_year = datetime.now().year
    # 如果当前时间在9月份之后，届别年份+1
    if datetime.now().month >= 9:
        current_year += 1

    grade_years = {
        '高三': f"{current_year}-H",      # 高中用 H 标识
        '高二': f"{current_year + 1}-H",
        '高一': f"{current_year + 2}-H",
        '初三': f"{current_year}-M",      # 初中用 M 标识
        '初二': f"{current_year + 1}-M",
        '初一': f"{current_year + 2}-M",
        '六年级': f"{current_year}-P",    # 小学用 P 标识
        '五年级': f"{current_year + 1}-P",
        '四年级': f"{current_year + 2}-P",
        '三年级': f"{current_year + 3}-P",
        '二年级': f"{current_year + 4}-P",
        '一年级': f"{current_year + 5}-P",
    }
    # 历史毕业班（过去3年的毕业生）
    history_grades = {}
    for year_offset in range(1, 4):  # 过去3年
        grad_year = current_year - year_offset
        history_grades[f'{grad_year}届高中'] = f"{grad_year}-H"
        history_grades[f'{grad_year}届初中'] = f"{grad_year}-M"
        history_grades[f'{grad_year}届小学'] = f"{grad_year}-P"

    context = {
        'module_name': module_names.get(module_type, '未知模块'),
        'module_type': module_type,
        'grade_years': grade_years,  # 传递年级和届别的对应关系
        'history_grades': history_grades,  # 传递历史毕业班数据
    }
    return render(request, 'client/grade_select.html', context)

def exam_select(request, module_type, grade):
    """考试选择视图函数，处理不同模块的考试选择逻辑。

    对于增值评价模块，直接重定向到对应学段的增值评价分析页面；
    对于其他模块，显示考试列表供选择。

    Args:
        request: HTTP请求对象
        module_type: 模块类型，可选值包括'value_added'/'overview'/'area'/'tracking'
        grade: 对于增值评价模块，是学段代码(H/M/P)；对于其他模块，是年级-学段格式(如2025-H)

    Returns:
        对于增值评价模块：重定向到增值评价分析页面
        对于其他模块：返回渲染后的考试选择页面

    Raises:
        ValueError: 当grade参数格式不正确时抛出
    """
    # 特殊处理增值评价模块
    if module_type == 'value_added':
        school_level = grade  # 直接使用传入的 H/M/P
        # 重定向到增值评价分析页面
        return redirect(reverse('score_analysis:value_added_detail', kwargs={
            'school_level': school_level
        }))

    # 其他模块的处理逻辑
    # 统一处理格式：year-school_level
    year, school_level = grade.split('-')
    grade_level = year
    level_suffix = {
        'H': '-H-',
        'M': '-M-',
        'P': '-P-'
    }

    with connection.cursor() as cursor:
        query = """
            SELECT 
                exam_id,
                exam_name,
                exam_date,
                exam_type,
                semester as current_grade
            FROM base_exam_config 
            WHERE status IN ('draft', 'published')
              AND grade_level = %s
              AND exam_id LIKE %s
            ORDER BY exam_date DESC
        """
        # 统一查询模式
        pattern = f"%{level_suffix[school_level]}{grade_level}"

        cursor.execute(query, [
            grade_level,
            pattern
        ])

        exams = cursor.fetchall()

    exam_list = []
    for exam_id, exam_name, exam_date, exam_type, current_grade in exams:
        exam_info = {
            'exam_id': exam_id,
            'exam_name': exam_name,
            'exam_date': exam_date,
            'exam_type': exam_type,
            'current_grade': current_grade
        }
        exam_list.append(exam_info)

    context = {
        'module_type': module_type,
        'grade': year,
        'school_level': {
            'H': '高中',
            'M': '初中',
            'P': '小学'
        }[school_level],
        'exams': exam_list
    }
    return render(request, 'client/exam_select.html', context)
# client/views.py

def analysis_view(request, module_type, exam_id):
    """分析视图
    @param module_type: 模块类型（overview/area/value_added/tracking）
    @param exam_id: 考试ID（如：202411-DIST-H-2025）
    """
    try:
        # 获取考试信息
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    exam_name,
                    exam_date,
                    exam_type,
                    semester as current_grade
                FROM base_exam_config 
                WHERE exam_id = %s
            """, [exam_id])
            exam_info = cursor.fetchone()

        if not exam_info:
            return render(request, 'error.html', {
                'error_message': '未找到考试信息'
            })

        # 模块重定向配置
        MODULE_REDIRECTS = {
            'overview': {
                'namespace': 'score_analysis',
                'view_name': 'exam_overview',  # 修改这里，使用正确的URL name
                'params': ['exam_id']  # 添加必要的参数
            },
            'area': {
                'namespace': 'score_analysis',
                'view_name': 'layer_view',
                'params': ['exam_id']
            },
            'value_added': {
                'namespace': 'score_analysis',
                'view_name': 'view_value_added',
            },
            'tracking': {
                'namespace': 'score_analysis',
                'view_name': 'view_development',
            }
        }

        module_config = MODULE_REDIRECTS.get(module_type)
        if not module_config:
            return render(request, 'error.html', {
                'error_message': f'未知的分析模块类型: {module_type}'
            })

        # 直接使用完整的 exam_id 重定向
        redirect_url = reverse(
            f"{module_config['namespace']}:{module_config['view_name']}",
            kwargs={
                'module_type': module_type,
                'exam_id': exam_id
            }
        )
        return redirect(redirect_url)

    except Exception as e:
        return render(request, 'error.html', {
            'error_message': f'分析视图处理失败: {str(e)}'
        })