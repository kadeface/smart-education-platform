# score_analysis/services/t_score_calculator.py

import pandas as pd
import numpy as np
from typing import Dict, List
import logging
from django.db import transaction
from ..models.t_score import SubjectTScore, SubjectStatistics


class TScoreCalculator:
    """T分数计算服务"""

    def __init__(self, exam_id: str):
        self.exam_id = exam_id
        self.logger = logging.getLogger(__name__)

    def calculate_exam_t_scores(self):
        """处理整个考试的T分计算"""
        try:
            self.logger.info(f"开始处理考试 {self.exam_id} 的T分计算")

            # 获取需要处理的科目
            subjects = self._get_subjects()

            for subject in subjects:
                self.logger.info(f"开始处理科目: {subject.subject_id}")
                self._process_subject(subject.subject_id)

        except Exception as e:
            self.logger.error(f"处理考试 {self.exam_id} T分计算时发生错误: {str(e)}")
            raise

    def _process_subject(self, subject_id: str):
        """处理单个科目的T分计算"""
        # 获取原始成绩数据
        scores_df = self._get_source_scores(subject_id)

        # 处理不同层级
        for level_type in ['city', 'district', 'school']:
            self._process_level(scores_df, subject_id, level_type)

    def _get_source_scores(self, subject_id: str) -> pd.DataFrame:
        """获取原始成绩数据"""
        # TODO: 实现从source_scores表获取数据的逻辑
        pass

    def _process_level(self, scores_df: pd.DataFrame, subject_id: str, level_type: str):
        """处理特定层级的T分计算"""
        # 按层级分组
        groups = self._group_by_level(scores_df, level_type)

        # 处理每个组
        for group_id, group_df in groups.items():
            self._process_group(group_df, subject_id, group_id, level_type)

    @transaction.atomic
    def _process_group(self, group_df: pd.DataFrame, subject_id: str, group_id: str, level_type: str):
        """处理单个组的T分计算"""
        try:
            # 计算统计值
            stats = self._calculate_statistics(group_df)

            # 保存统计值
            self._save_statistics(subject_id, group_id, level_type, stats)

            # 计算并保存T分
            self._calculate_and_save_t_scores(group_df, stats, subject_id, group_id, level_type)

        except Exception as e:
            self.logger.error(f"处理组 {group_id} 时发生错误: {str(e)}")
            raise

    def _calculate_statistics(self, scores: pd.Series) -> Dict:
        """计算统计值"""
        return {
            'sample_size': len(scores),
            'mean': scores.mean(),
            'std_dev': scores.std()
        }

    def _calculate_t_score(self, score: float, mean: float, std_dev: float) -> float:
        """计算单个T分"""
        if std_dev == 0:
            return 50  # 处理标准差为0的情况

        z_score = (score - mean) / std_dev
        return 50 + (z_score * 10)