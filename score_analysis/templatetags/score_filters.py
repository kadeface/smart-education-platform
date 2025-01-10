from django import template

register = template.Library()

@register.filter
def get_attr(obj, attr):
    """获取对象的属性值"""
    return getattr(obj, attr, None)

@register.filter
def get_item(dictionary, key):
    """获取字典中的值"""
    if not dictionary:
        return None
    return dictionary.get(key)

@register.filter
def multiply(value, arg):
    """将值乘以参数"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ''