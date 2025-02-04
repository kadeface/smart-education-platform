# your_app/templatetags/custom_filters.py

from django import template
register = template.Library()
import json
@register.filter
def get(value, key):
    """获取字典中的值，处理字符串和字典"""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if isinstance(value, dict):
        return value.get(key)
    return None

@register.filter
def split(value, delimiter=','):
    """分割字符串"""
    if value:
        return value.split(delimiter)
    return []

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    获取字典中的值
    """
    return dictionary.get(key, 0)

@register.filter
def school_short_name(name):
    """将学校全称转换为简称"""
    name_mapping = {
        '开平市开侨中学': '开侨',
        '开平市第一中学': '一中',
        '开平市教伦中学': '教伦',
        '开平市忠源纪念中学': '忠源',
        '开平市风采中学': '风采',
        '开平市风采华侨中学': '风侨',
        '开平市第二中学': '二中',
        '开平市长师中学': '长师'
    }
    return name_mapping.get(name, name)  # 如果没有映射关系，返回原名