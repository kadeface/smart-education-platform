# DjangoProject1/test_t_score.py
import os
import sys
import logging
from datetime import datetime

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'score_analysis_project.settings')

import django

django.setup()

from score_analysis.services.t_score_calculator import TScoreCalculator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_t_score():
    try:
        # 初始化计算器
        calculator = TScoreCalculator(exam_id='202401-CITY-H')

        # 执行计算
        calculator.calculate()

        logger.info("T分计算完成")

    except Exception as e:
        logger.error(f"T分计算错误: {str(e)}")


if __name__ == '__main__':
    test_t_score()