from django import template

register = template.Library()

@register.filter
def get_attr(obj, attr):
    """获取对象的属性值"""
    return getattr(obj, attr, None)