# test_rankings.py
import os
import sys
import logging
from datetime import datetime

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'score_analysis_project.settings')

import django

django.setup()

import pandas as pd
from score_analysis.models import (
    ScoreStudentBasic,
    SubjectTScore,
    ScoreRankings
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def calculate_rankings(exam_id: str):
    """计算排名"""
    try:
        # 处理每个科目
        subjects = ['chinese', 'math', 'english', 'physics', 'chemistry',
                    'biology', 'history', 'politics', 'geography']

        for subject in subjects:
            logger.info(f"开始处理科目: {subject} 的排名")

            # 获取原始分数据
            scores = ScoreStudentBasic.objects.filter(
                exam_id=exam_id
            ).values('student_id', 'select_type', subject, 'district_name', 'school_name')

            df = pd.DataFrame(scores)
            if df.empty:
                continue

            # 重命名列
            df = df.rename(columns={subject: 'raw_score'})
            df['raw_score'] = df['raw_score'].astype(float)

            # 计算市级排名
            calculate_level_rankings(df, exam_id, subject, 'city')

            # 计算区级排名
            calculate_level_rankings(df, exam_id, subject, 'district')

            # 计算校级排名
            calculate_level_rankings(df, exam_id, subject, 'school')

        logger.info("排名计算完成")

    except Exception as e:
        logger.error(f"排名计算错误: {str(e)}")
        raise


def calculate_level_rankings(df: pd.DataFrame, exam_id: str, subject_id: str, level_type: str):
    """计算指定层级的排名"""
    try:
        # 根据层级分组
        if level_type == 'city':
            groups = {'city': df}
        elif level_type == 'district':
            groups = dict(tuple(df.groupby('district_name')))
        else:  # school level
            groups = dict(tuple(df.groupby(['district_name', 'school_name'])))

        for group_id, group_df in groups.items():
            # 处理文理科分组
            for stream_type, stream_df in group_df.groupby('select_type'):
                # 计算排名
                stream_df['rank'] = stream_df['raw_score'].rank(method='min', ascending=False)
                total_count = len(stream_df)
                stream_df['percentile'] = (stream_df['rank'] / total_count * 100).round(2)

                # 保存排名结果
                rankings = []
                for _, row in stream_df.iterrows():
                    rankings.append(ScoreRankings(
                        exam_id=exam_id,
                        unified_student_id=row['student_id'],
                        subject_id=subject_id,
                        stream_type=stream_type,
                        level_type=level_type,
                        raw_score=row['raw_score'],
                        raw_score_rank=int(row['rank']),
                        total_count=total_count,
                        percentile=row['percentile']
                    ))

                # 批量保存
                ScoreRankings.objects.bulk_create(rankings)

                logger.info(f"{level_type} {group_id} {stream_type} {subject_id} 排名计算完成")

    except Exception as e:
        logger.error(f"计算 {level_type} 排名时发生错误: {str(e)}")
        raise


if __name__ == '__main__':
    test_exam_id = 'TEST001'  # 替换为实际的考试ID
    calculate_rankings(test_exam_id)