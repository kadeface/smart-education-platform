# score_analysis/services/ranking_calculator.py

import pandas as pd
import numpy as np
import logging
from typing import Dict, List
from django.db import transaction
from ..models import (
    ScoreStudentBasic,
    ScoreRankings
)


class RankingCalculator:
    """排名计算服务类"""

    def __init__(self, exam_id: str):
        self.exam_id = exam_id
        self.logger = logging.getLogger(__name__)

    def calculate(self):
        """计算排名"""
        try:
            # 处理每个科目
            subjects = ['chinese', 'math', 'english', 'physics', 'chemistry',
                        'biology', 'history', 'politics', 'geography']

            for subject in subjects:
                self.logger.info(f"开始处理科目: {subject} 的排名")

                # 获取原始分数据
                scores = ScoreStudentBasic.objects.filter(
                    exam_id=self.exam_id
                ).values('student_id', 'select_type', subject, 'district_name', 'school_name')

                df = pd.DataFrame(scores)
                if df.empty:
                    continue

                # 重命名列
                df = df.rename(columns={subject: 'raw_score'})
                df['raw_score'] = df['raw_score'].astype(float)

                # 计算各层级排名
                for level_type in ['city', 'district', 'school']:
                    self._calculate_level_rankings(df, subject, level_type)

            self.logger.info("排名计算完成")

        except Exception as e:
            self.logger.error(f"排名计算错误: {str(e)}")
            raise

    def _calculate_level_rankings(self, df: pd.DataFrame, subject_id: str, level_type: str):
        """计算指定层级的排名"""
        try:
            # 根据层级分组
            if level_type == 'city':
                groups = {'city': df}
            elif level_type == 'district':
                groups = dict(tuple(df.groupby('district_name')))
            else:  # school level
                groups = dict(tuple(df.groupby(['district_name', 'school_name'])))

            # 处理每个分组
            for group_id, group_df in groups.items():
                # 处理文理科分组
                for stream_type, stream_df in group_df.groupby('select_type'):
                    # 计算排名
                    stream_df['rank'] = stream_df['raw_score'].rank(method='min', ascending=False)
                    total_count = len(stream_df)
                    stream_df['percentile'] = (stream_df['rank'] / total_count * 100).round(2)

                    # 保存排名结果
                    self._save_rankings(
                        subject_id=subject_id,
                        level_type=level_type,
                        stream_type=stream_type,
                        rankings_df=stream_df
                    )

                    self.logger.info(f"{level_type} {group_id} {stream_type} {subject_id} 排名计算完成")

        except Exception as e:
            self.logger.error(f"计算 {level_type} 排名时发生错误: {str(e)}")
            raise

    @transaction.atomic
    def _save_rankings(self, subject_id: str, level_type: str,
                       stream_type: str, rankings_df: pd.DataFrame):
        """保存排名结果"""
        try:
            rankings = []
            for _, row in rankings_df.iterrows():
                rankings.append(
                    ScoreRankings(
                        exam_id=self.exam_id,
                        unified_student_id=row['student_id'],
                        subject_id=subject_id,
                        stream_type=stream_type,
                        level_type=level_type,
                        raw_score=row['raw_score'],
                        raw_score_rank=int(row['rank']),
                        total_count=len(rankings_df),
                        percentile=row['percentile']
                    )
                )

            # 批量保存
            ScoreRankings.objects.bulk_create(rankings)

        except Exception as e:
            self.logger.error(f"保存排名结果时发生错误: {str(e)}")
            raise


    def calculate_total_score(self, scores_df: pd.DataFrame, stream_type: str) -> pd.DataFrame:
        """
        计算总分
        Args:
            scores_df: 包含所有科目分数的DataFrame
            stream_type: 文科/理科
        Returns:
            DataFrame: 增加total_score列的DataFrame
        """
        try:
            # 将所有成绩转为float
            score_columns = ['chinese', 'math', 'english', 'physics', 'chemistry',
                             'biology', 'history', 'politics', 'geography']
            for col in score_columns:
                scores_df[col] = scores_df[col].astype(float)

            # 计算必考科目总分（语数外）
            total_scores = (
                    scores_df['chinese'] +
                    scores_df['math'] +
                    scores_df['english']
            )

            # 根据文理科添加分科标识科目
            if stream_type == '理科':
                total_scores += scores_df['physics']
                optional_subjects = ['chemistry', 'biology', 'politics', 'geography']
            else:  # 文科
                total_scores += scores_df['history']
                optional_subjects = ['politics', 'geography', 'chemistry', 'biology']

            # 计算选考科目总分（取最高两门）
            optional_scores = scores_df[optional_subjects].values
            top_two_scores = np.sort(optional_scores)[:, -2:]  # 取每行最高的两个分数
            total_scores += top_two_scores.sum(axis=1)

            return total_scores

        except Exception as e:
            self.logger.error(f"计算总分时发生错误: {str(e)}")
            raise


    def calculate_total_rankings(self, df: pd.DataFrame):
        """计算总分排名"""
        try:
            # 分文理科处理
            for stream_type in ['理科', '文科']:
                # 筛选文理科学生
                stream_df = df[df['select_type'] == stream_type].copy()
                if stream_df.empty:
                    continue

                # 计算总分
                stream_df['total_score'] = self.calculate_total_score(stream_df, stream_type)

                # 计算各层级排名
                for level_type in ['city', 'district', 'school']:
                    self._calculate_total_level_rankings(
                        stream_df, stream_type, level_type
                    )

        except Exception as e:
            self.logger.error(f"计算总分排名时发生错误: {str(e)}")
            raise


    def _calculate_total_level_rankings(self, df: pd.DataFrame, stream_type: str, level_type: str):
        """计算指定层级的总分排名"""
        try:
            # 根据层级分组
            if level_type == 'city':
                groups = {'city': df}
            elif level_type == 'district':
                groups = dict(tuple(df.groupby('district_name')))
            else:  # school level
                groups = dict(tuple(df.groupby(['district_name', 'school_name'])))

            # 处理每个分组
            for group_id, group_df in groups.items():
                # 计算排名
                group_df['rank'] = group_df['total_score'].rank(method='min', ascending=False)
                total_count = len(group_df)
                group_df['percentile'] = (group_df['rank'] / total_count * 100).round(2)

                # 保存排名结果
                self._save_total_rankings(
                    level_type=level_type,
                    stream_type=stream_type,
                    rankings_df=group_df
                )

                self.logger.info(f"总分 {level_type} {group_id} {stream_type} 排名计算完成")

        except Exception as e:
            self.logger.error(f"计算总分 {level_type} 排名时发生错误: {str(e)}")
            raise


    def _save_total_rankings(self, level_type: str, stream_type: str, rankings_df: pd.DataFrame):
        """保存总分排名结果"""
        try:
            with transaction.atomic():
                rankings = []
                for _, row in rankings_df.iterrows():
                    rankings.append(
                        ScoreRankings(
                            exam_id=self.exam_id,
                            unified_student_id=row['student_id'],
                            subject_id='total',  # 使用'total'表示总分
                            stream_type=stream_type,
                            level_type=level_type,
                            raw_score=row['total_score'],
                            raw_score_rank=int(row['rank']),
                            total_count=len(rankings_df),
                            percentile=row['percentile']
                        )
                    )

                # 批量保存
                ScoreRankings.objects.bulk_create(rankings)

        except Exception as e:
            self.logger.error(f"保存总分排名结果时发生错误: {str(e)}")
            raise


    def calculate(self):
        """主计算方法"""
        try:
            # 1. 先计算单科排名
            subjects = ['chinese', 'math', 'english', 'physics', 'chemistry',
                        'biology', 'history', 'politics', 'geography']

            for subject in subjects:
                self.logger.info(f"开始处理科目: {subject} 的排名")
                scores = self._get_subject_scores(subject)
                if not scores.empty:
                    self._calculate_subject_rankings(scores, subject)

            # 2. 计算总分排名
            self.logger.info("开始计算总分排名")
            all_scores = self._get_all_scores()
            self.calculate_total_rankings(all_scores)

            self.logger.info("所有排名计算完成")

        except Exception as e:
            self.logger.error(f"排名计算错误: {str(e)}")
            raise