from django.core.cache import cache
from django.db import transaction
import statistics

class BaseService:
    """基础服务类"""
    def __init__(self):
        self.cache_timeout = 3600  # 缓存时间1小时

    def _get_cache_key(self, prefix, id_value):
        return f"{prefix}_{id_value}"

    def _calculate_slope(self, x, y):
        """计算线性回归斜率"""
        if len(x) != len(y) or len(x) < 2:
            return 0
        n = len(x)
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denominator = sum((x[i] - mean_x) ** 2 for i in range(n))
        return numerator / denominator if denominator != 0 else 0

    def _calculate_stability(self, scores):
        """计算稳定性得分"""
        if not scores or len(scores) < 2:
            return None
        std_dev = statistics.stdev(scores) if len(scores) > 1 else 0
        mean = statistics.mean(scores)
        return round(100 - (std_dev / mean * 100), 2) if mean != 0 else 0