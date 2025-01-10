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