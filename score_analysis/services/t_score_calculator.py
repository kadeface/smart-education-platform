# score_analysis/services/t_score_calculator.py

import pandas as pd
import numpy as np
import logging
from typing import Dict, List
from django.db import transaction
from ..models import (
   ScoreStudentBasic,
   SubjectTScore,
   SubjectStatistics
)
class TScoreCalculator:
    """
    T分数计算类
    """
    def __init__(self, exam_id: str):
        """
        初始化TScoreCalculator
        Args:
            exam_id: 考试ID
        """
        self.exam_id = exam_id
        self.logger = logging.getLogger(__name__)
    def calculate(self):
        """
        计算T分数
        """
    def _get_source_scores(self, subject_id: str) -> pd.DataFrame:
        """
        获取原始成绩数据

        Args:
            subject_id: 科目ID
        Returns:
            pd.DataFrame: 包含unified_student_id、raw_score、stream_type等字段的DataFrame
        """
        try:
            # 定义需要区分文理科的科目
            stream_diff_subjects = {'physics', 'history'}

            # 从基础成绩表获取数据
            scores = ScoreStudentBasic.objects.filter(
                exam_id=self.exam_id
            ).values(
                'student_id',  # 统一考号
                'select_type',  # 文理科
                subject_id,  # 科目成绩
                'district_name',
                'school_name'
            )

            # 转换为DataFrame
            df = pd.DataFrame(scores)

            if df.empty:
                self.logger.warning(f"考试 {self.exam_id} 未找到成绩数据")
                return pd.DataFrame()

            # 重命名列
            df = df.rename(columns={
                subject_id: 'raw_score',
                'student_id': 'unified_student_id'
            })

            # 处理空值
            df = df.dropna(subset=['raw_score'])

            # 设置stream_type
            if subject_id in stream_diff_subjects:
                # physics和history需要使用select_type
                df['stream_type'] = df['select_type']
            else:
                # 其他科目不区分文理科
                df['stream_type'] = '未确定'

            self.logger.info(f"获取到 {len(df)} 条有效成绩数据")

            return df

        except Exception as e:
            self.logger.error(f"获取成绩数据时发生错误: {str(e)}")
            raise


    def _process_level(self, scores_df: pd.DataFrame, subject_id: str, level_type: str):
        """
        处理特定层级的T分计算

        Args:
            scores_df: 原始分数DataFrame
            subject_id: 科目ID
            level_type: 分析层级（city/district/school）
        """
        try:
            # 根据层级类型进行分组
            if level_type == 'city':
                # 市级层面作为一个整体处理
                groups = {'city': scores_df}
            elif level_type == 'district':
                # 按区县分组
                groups = dict(tuple(scores_df.groupby('district_name')))
            else:  # school level
                # 按学校分组
                groups = dict(tuple(scores_df.groupby(['district_name', 'school_name'])))

            self.logger.info(f"{level_type}层级共有 {len(groups)} 个分组")

            # 处理每个分组
            for group_id, group_df in groups.items():
                # 检查样本量
                if len(group_df) < 10:  # 设置最小样本量要求
                    self.logger.warning(f"分组 {group_id} 样本量不足: {len(group_df)}")
                    continue

                try:
                    self._process_group(group_df, subject_id, group_id, level_type)
                except Exception as e:
                    self.logger.error(f"处理分组 {group_id} 时发生错误: {str(e)}")
                    continue

        except Exception as e:
            self.logger.error(f"处理{level_type}层级时发生错误: {str(e)}")
            raise


    def _calculate_statistics(self, df: pd.DataFrame) -> Dict:
        """
        计算统计值

        Args:
            df: 包含raw_score的DataFrame
        Returns:
            Dict: 包含mean、std_dev、sample_size的统计值字典
        """
        try:
            # 确保有足够的样本
            sample_size = len(df)
            if sample_size < 10:
                raise ValueError(f"样本量不足: {sample_size}")

            # 计算统计值
            raw_scores = df['raw_score']
            stats = {
                'sample_size': sample_size,
                'mean': float(raw_scores.mean()),
                'std_dev': float(raw_scores.std())
            }

            # 验证计算结果
            if pd.isna(stats['mean']) or pd.isna(stats['std_dev']):
                raise ValueError("统计值计算结果含有空值")

            if stats['std_dev'] == 0:
                self.logger.warning("标准差为0，所有分数相同")
                # 标准差为0时，设置一个很小的值以避免除以0
                stats['std_dev'] = 0.0001

            self.logger.info(
                f"计算得到统计值: mean={stats['mean']:.2f}, std_dev={stats['std_dev']:.2f}, n={stats['sample_size']}")

            return stats

        except Exception as e:
            self.logger.error(f"计算统计值时发生错误: {str(e)}")
            raise


    def _save_statistics(self, subject_id: str, group_id: str, level_type: str, stream_type: str, stats: Dict):
        """
        保存统计值

        Args:
            subject_id: 科目ID
            group_id: 分组标识
            level_type: 分析层级
            stream_type: 文科/理科/未确定
            stats: 统计值字典
        """
        try:
            with transaction.atomic():
                # 尝试更新已存在的记录
                updated = SubjectStatistics.objects.filter(
                    exam_id=self.exam_id,
                    subject_id=subject_id,
                    level_type=level_type,
                    stream_type=stream_type
                ).update(
                    sample_size=stats['sample_size'],
                    mean=stats['mean'],
                    std_dev=stats['std_dev']
                )

                # 如果没有更新到记录，创建新记录
                if not updated:
                    SubjectStatistics.objects.create(
                        exam_id=self.exam_id,
                        subject_id=subject_id,
                        level_type=level_type,
                        stream_type=stream_type,
                        sample_size=stats['sample_size'],
                        mean=stats['mean'],
                        std_dev=stats['std_dev']
                    )

                self.logger.info(
                    f"已保存统计值 - 科目:{subject_id}, 层级:{level_type}, "
                    f"类型:{stream_type}, 均值:{stats['mean']:.2f}, "
                    f"标准差:{stats['std_dev']:.2f}"
                )

        except Exception as e:
            self.logger.error(f"保存统计值时发生错误: {str(e)}")
            raise


    def _calculate_and_save_t_scores(self, df: pd.DataFrame, stats: Dict, subject_id: str,
                                     group_id: str, level_type: str, stream_type: str):
        """
        计算并保存T分数

        Args:
            df: 原始分数DataFrame
            stats: 统计值字典
            subject_id: 科目ID
            group_id: 分组标识
            level_type: 分析层级
            stream_type: 文科/理科/未确定
        """
        try:
            # 计算Z分数和T分数
            z_scores = (df['raw_score'] - stats['mean']) / stats['std_dev']
            t_scores = 50 + (10 * z_scores)

            # 准备批量创建的数据
            t_score_records = []
            for idx, row in df.iterrows():
                t_score_records.append(
                    SubjectTScore(
                        exam_id=self.exam_id,
                        unified_student_id=row['unified_student_id'],
                        subject_id=subject_id,
                        stream_type=stream_type,
                        level_type=level_type,
                        raw_score=row['raw_score'],
                        z_score=round(z_scores[idx], 2),
                        t_score=round(t_scores[idx], 1)
                    )
                )

            # 批量保存
            with transaction.atomic():
                # 删除已存在的记录
                SubjectTScore.objects.filter(
                    exam_id=self.exam_id,
                    subject_id=subject_id,
                    level_type=level_type,
                    stream_type=stream_type,
                    unified_student_id__in=df['unified_student_id'].tolist()
                ).delete()

                # 批量创建新记录
                SubjectTScore.objects.bulk_create(t_score_records)

            self.logger.info(
                f"已保存T分 - 科目:{subject_id}, 层级:{level_type}, "
                f"类型:{stream_type}, 数量:{len(t_score_records)}"
            )

        except Exception as e:
            self.logger.error(f"计算保存T分时发生错误: {str(e)}")
            raise