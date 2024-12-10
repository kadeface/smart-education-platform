from django import template
from django.template.defaultfilters import register
from ..models.base import BaseSubjectConfig

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """获取字典中的值"""
    return dictionary.get(key)
'''
@register.filter
def stream_type_name(select_type):
    """将文理科类型代码转换为显示名称"""
    names = {
        'arts': '文科',
        'science': '理科',
        # 可以根据需要添加更多映射
    }
    return names.get(select_type, select_type)
'''
@register.filter
def subject_name(subject_id):
    """将科目ID转换为科目名称"""
    try:
        subject = BaseSubjectConfig.objects.get(subject_id=subject_id)
        return subject.subject_name
    except BaseSubjectConfig.DoesNotExist:
        # 如果找不到科目配置，返回原始ID
        return subject_id

@register.filter
def format_score(value):
    """格式化分数，保留一位小数"""
    try:
        return f"{float(value):.1f}"
    except (ValueError, TypeError):
        return value

@register.filter
def percentage(value):
    """将小数转换为百分比"""
    try:
        return f"{float(value):.1f}%"
    except (ValueError, TypeError):
        return value