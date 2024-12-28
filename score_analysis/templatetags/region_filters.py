# score_analysis/templatetags/region_filters.py

from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def format_score(value):
    """格式化分数"""
    try:
        if value is None or value == '':
            return '-'
        if isinstance(value, str):
            value = float(value)
        return f"{value:.1f}"
    except (ValueError, TypeError):
        return '-'

@register.filter
def format_ratio(value):
    """格式化比例"""
    try:
        if value is None or value == '':
            return '-'
        if isinstance(value, str):
            value = float(value)
        return f"{value :.1f}%"
    except (ValueError, TypeError):
        return '-'

@register.filter
def get_item(dictionary, key):
    """获取字典项"""
    try:
        return dictionary.get(key, {})
    except (AttributeError, KeyError):
        return {}

@register.filter
def subtract(value, arg):
    """计算两个数的差值"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def format_diff(value):
    """格式化差值，添加正负号"""
    try:
        if value > 0:
            return f"+{value:.2f}"
        return f"{value:.2f}"
    except (ValueError, TypeError):
        return "-"