# score_analysis/services/statistics_calculator.py

import pandas as pd
import numpy as np
import logging
from typing import Dict, List
from django.db import transaction
from ..models import ScoreStudentBasic, ScoreRankings

class StatisticsCalculator:
    """统计分析服务类"""

    def __init__(self, exam_id: str):
        self.exam_id = exam_id
        self.logger = logging.getLogger(__name__)

    def calculate_basic_statistics(self) -> Dict:
        """计算基础统计数据"""
        try:
            # 1. 获取考试数据
            scores = ScoreStudentBasic.objects.filter(
                exam_id=self.exam_id
            ).values(
                'student_id', 'select_type', 'district_name', 'school_name',
                'chinese', 'math', 'english', 'physics', 'chemistry',
                'biology', 'history', 'politics', 'geography'
            )
            df = pd.DataFrame(scores)

            if df.empty:
                return {}

            # 2. 计算基础统计信息
            stats = {
                'student_count': self._calculate_student_counts(df),
                'stream_distribution': self._calculate_stream_distribution(df),
                'subject_statistics': self._calculate_subject_statistics(df),
                'district_statistics': self._calculate_district_statistics(df)
            }

            return stats

        except Exception as e:
            self.logger.error(f"计算基础统计时发生错误: {str(e)}")
            raise

    def _calculate_student_counts(self, df: pd.DataFrame) -> Dict:
        """统计学生人数"""
        try:
            total_count = len(df)
            district_counts = df.groupby('district_name').size().to_dict()
            school_counts = df.groupby(['district_name', 'school_name']).size().to_dict()

            return {
                'total': total_count,
                'by_district': district_counts,
                'by_school': school_counts
            }

        except Exception as e:
            self.logger.error(f"计算学生人数时发生错误: {str(e)}")
            raise

    def _calculate_stream_distribution(self, df: pd.DataFrame) -> Dict:
        """计算文理科分布"""
        try:
            stream_counts = df['select_type'].value_counts().to_dict()
            stream_percentages = (df['select_type'].value_counts(normalize=True) * 100).round(2).to_dict()

            return {
                'counts': stream_counts,
                'percentages': stream_percentages
            }

        except Exception as e:
            self.logger.error(f"计算文理科分布时发生错误: {str(e)}")
            raise

    def _calculate_subject_statistics(self, df: pd.DataFrame) -> Dict:
        """计算各科目统计数据"""
        try:
            subjects = ['chinese', 'math', 'english', 'physics', 'chemistry',
                        'biology', 'history', 'politics', 'geography']

            stats = {}
            for subject in subjects:
                subject_scores = df[subject].astype(float)
                stats[subject] = {
                    'mean': round(subject_scores.mean(), 2),
                    'std': round(subject_scores.std(), 2),
                    'max': subject_scores.max(),
                    'min': subject_scores.min(),
                    'count': len(subject_scores.dropna())
                }

            return stats

        except Exception as e:
            self.logger.error(f"计算科目统计时发生错误: {str(e)}")
            raise

    def _calculate_district_statistics(self, df: pd.DataFrame) -> Dict:
        """计算区域统计数据"""
        try:
            district_stats = df.groupby('district_name').agg({
                'student_id': 'count',
                'school_name': 'nunique'
            }).to_dict('index')

            return district_stats

        except Exception as e:
            self.logger.error(f"计算区域统计时发生错误: {str(e)}")
            raise

    def calculate_score_segments(self) -> Dict:
        """计算分数段统计"""
        try:
            # 使用排名表获取数据
            rankings = ScoreRankings.objects.filter(
                exam_id=self.exam_id
            ).values(
                'subject_id', 'stream_type', 'level_type',
                'raw_score', 'percentile'
            )

            df = pd.DataFrame(rankings)
            if df.empty:
                return {}

            segments = {
                'top_10': self._calculate_top_segment(df, 10),
                'top_30': self._calculate_top_segment(df, 30),
                'middle': self._calculate_middle_segment(df),
                'bottom_30': self._calculate_bottom_segment(df, 30)
            }

            return segments

        except Exception as e:
            self.logger.error(f"计算分数段统计时发生错误: {str(e)}")
            raise

    def _calculate_top_segment(self, df: pd.DataFrame, percent: int) -> Dict:
        """计算前N%的统计数据"""
        try:
            top_df = df[df['percentile'] <= percent]

            stats = self._calculate_segment_statistics(top_df, f'top_{percent}')
            return stats

        except Exception as e:
            self.logger.error(f"计算前{percent}%统计时发生错误: {str(e)}")
            raise

    def _calculate_middle_segment(self, df: pd.DataFrame) -> Dict:
        """计算中间段(30%-70%)的统计数据"""
        try:
            middle_df = df[(df['percentile'] > 30) & (df['percentile'] <= 70)]

            stats = self._calculate_segment_statistics(middle_df, 'middle')
            return stats

        except Exception as e:
            self.logger.error(f"计算中间段统计时发生错误: {str(e)}")
            raise

    def _calculate_bottom_segment(self, df: pd.DataFrame, percent: int) -> Dict:
        """计算后N%的统计数据"""
        try:
            bottom_df = df[df['percentile'] > (100 - percent)]

            stats = self._calculate_segment_statistics(bottom_df, f'bottom_{percent}')
            return stats

        except Exception as e:
            self.logger.error(f"计算后{percent}%统计时发生错误: {str(e)}")
            raise

    def _calculate_segment_statistics(self, df: pd.DataFrame, segment_name: str) -> Dict:
        """计算分段统计数据"""
        try:
            stats = df.groupby(['subject_id', 'stream_type']).agg({
                'raw_score': ['count', 'mean', 'std', 'min', 'max']
            }).round(2).to_dict()

            return {
                'segment': segment_name,
                'statistics': stats
            }

        except Exception as e:
            self.logger.error(f"计算分段统计数据时发生错误: {str(e)}")
            raise