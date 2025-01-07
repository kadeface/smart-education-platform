import numpy as np
import pandas as pd
from django.db import connection
from typing import List, Dict, Tuple

from django.db.models.fields import json


class RankingService:
    def generate_rankings(self, exam_id: str) -> bool:
        """生成排名数据的入口方法"""
        try:
            print(f"\n=== 开始生成考试ID: {exam_id} 的排名数据 ===")

            # 1. 获取原始数据
            df = pd.read_sql("""
                SELECT 
                    tr.*, 
                    ssb.district_name,
                    ssb.school_name,
                    ssb.chinese, ssb.math, ssb.english,
                    ssb.physics, ssb.chemistry, ssb.biology,
                    ssb.politics, ssb.history, ssb.geography
                FROM tracking_records tr
                JOIN score_student_basic ssb 
                    ON tr.student_id = ssb.student_id 
                    AND tr.exam_id = ssb.exam_id
                WHERE tr.exam_id = %s
            """, connection, params=[exam_id])

            if df.empty:
                print("错误：没有找到学生成绩数据")
                return False

            # 2. 计算排名
            df = self._calculate_rankings(df)

            # 3. 更新排名
            self._update_rankings(df)

            print("\n=== 排名数据生成完成！===")
            return True

        except Exception as e:
            print(f"\n=== 生成排名时发生错误: {str(e)} ===")
            raise

    def _calculate_rankings(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算排名"""
        # 按分科类型分组处理
        for select_type in df['select_type'].unique():
            select_mask = df['select_type'] == select_type
            select_df = df[select_mask].copy()

            # 1. 计算总分排名（市级、区县级、学校级）
            select_df['city_rank'] = self._calculate_rank(
                select_df, ['total_score', 'math', 'chinese']
            )

            select_df['district_rank'] = select_df.groupby('district_name').apply(
                lambda x: self._calculate_rank(x, ['total_score', 'math', 'chinese'])
            ).reset_index(level=0, drop=True)

            select_df['school_rank'] = select_df.groupby(['district_name', 'school_name']).apply(
                lambda x: self._calculate_rank(x, ['total_score', 'math', 'chinese'])
            ).reset_index(level=[0, 1], drop=True)

            # 2. 计算各科目排名
            subjects = {
                'chinese': ['chinese', 'total_score', 'math'],
                'math': ['math', 'total_score', 'chinese'],
                'english': ['english', 'total_score', 'math'],
                'physics': ['physics', 'total_score', 'math'],
                'chemistry': ['chemistry', 'total_score', 'math'],
                'biology': ['biology', 'total_score', 'math'],
                'politics': ['politics', 'total_score', 'math'],
                'history': ['history', 'total_score', 'math'],
                'geography': ['geography', 'total_score', 'math']
            }

            subject_ranks = {}
            for subject, sort_cols in subjects.items():
                if subject in select_df.columns:  # 只处理存在的科目
                    subject_ranks[subject] = {
                        'city': self._calculate_rank(select_df, sort_cols).tolist(),
                        'district': select_df.groupby('district_name').apply(
                            lambda x: self._calculate_rank(x, sort_cols)
                        ).reset_index(level=0, drop=True).tolist(),
                        'school': select_df.groupby(['district_name', 'school_name']).apply(
                            lambda x: self._calculate_rank(x, sort_cols)
                        ).reset_index(level=[0, 1], drop=True).tolist()
                    }

            # 更新 JSON 字段
            select_df['subject_ranks'] = select_df.apply(
                lambda row: {
                    subject: {
                        'city': ranks['city'][row.name],
                        'district': ranks['district'][row.name],
                        'school': ranks['school'][row.name]
                    }
                    for subject, ranks in subject_ranks.items()
                },
                axis=1
            )

            # 更新原始数据框
            df.loc[select_mask] = select_df

        return df

    def _calculate_rank(self, df: pd.DataFrame, sort_columns: List[str]) -> pd.Series:
        """计算排名"""
        # 过滤有效成绩
        valid_mask = df[sort_columns[0]] > 0
        if not valid_mask.any():
            return pd.Series(index=df.index)

        valid_df = df[valid_mask].copy()

        # 按指定列排序
        sorted_df = valid_df.sort_values(
            sort_columns,
            ascending=[False] * len(sort_columns)
        )

        # 返回排名
        ranks = pd.Series(range(1, len(sorted_df) + 1), index=sorted_df.index)
        return ranks.reindex(df.index)

    def _update_rankings(self, df: pd.DataFrame) -> None:
        """更新排名数据"""
        try:
            with connection.cursor() as cursor:
                # 准备更新数据
                update_data = []
                for _, row in df.iterrows():
                    update_data.append((
                        int(row['city_rank']) if pd.notna(row['city_rank']) else None,
                        int(row['district_rank']) if pd.notna(row['district_rank']) else None,
                        int(row['school_rank']) if pd.notna(row['school_rank']) else None,
                        json.dumps(row['subject_ranks']),
                        row['exam_id'],
                        row['student_id']
                    ))

                # 批量更新
                update_sql = """
                    UPDATE tracking_records 
                    SET 
                        city_rank = %s,
                        district_rank = %s,
                        school_rank = %s,
                        subject_ranks = %s
                    WHERE exam_id = %s 
                    AND student_id = %s
                """

                cursor.executemany(update_sql, update_data)
                print(f"已更新 {cursor.rowcount} 条排名记录")

                connection.commit()

        except Exception as e:
            print(f"更新排名数据时出错: {str(e)}")
            connection.rollback()
            raise