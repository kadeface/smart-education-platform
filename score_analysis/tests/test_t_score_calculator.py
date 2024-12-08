# test_t_score.py
import os
import sys
import logging
from datetime import datetime

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

# Django设置
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'score_analysis_project.settings')

# Django配置
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
        calculator = TScoreCalculator(exam_id='TEST001')

        # 执行计算
        calculator.calculate_exam_t_scores()

        logger.info("T分计算完成")

    except Exception as e:
        logger.error(f"T分计算错误: {str(e)}")


if __name__ == '__main__':
    test_t_score()