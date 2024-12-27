# templatetags/region_filters.py

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """获取字典中的值

    用法:
    {{ mydict|get_item:key }}
    """
    if not dictionary:
        return None
    return dictionary.get(key)


@register.filter
def get_layer_data(school_data, layer_type):
    """获取学校某个层次的数据

    用法:
    {{ school_data|get_layer_data:layer_type }}
    """
    if not school_data or 'layers' not in school_data:
        return None
    return school_data['layers'].get(layer_type)


@register.filter
def format_ratio(value):
    """格式化比例为百分数

    用法:
    {{ 0.1234|format_ratio }}  -> 12.34%
    """
    if value is None:
        return '0%'
    return f"{value * 100:.2f}%"


@register.filter
def format_score(value):
    """格式化分数，保留1位小数

    用法:
    {{ 89.666|format_score }}  -> 89.7
    """
    if value is None:
        return '-'
    return f"{value:.1f}"