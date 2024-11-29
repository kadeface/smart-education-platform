# score_processor/services/data_cleaner.py

import pandas as pd
import numpy as np


class DataCleanerService:
    def __init__(self):
        # 定义科目列表
        self.required_subjects = ['语文', '数学', '英语']
        self.optional_subjects = ['物理', '化学', '生物', '历史', '政治', '地理']
        self.all_subjects = self.required_subjects + self.optional_subjects

    def clean_data(self, df):
        """数据清洗主函数"""
        try:
            cleaning_stats = {
                '原始记录数': len(df)
            }

            # 先处理英语听说成绩
            if '英语听说' in df.columns:
                # 转换英语和英语听说为数值
                df['英语'] = pd.to_numeric(df['英语'], errors='coerce')
                df['英语听说'] = pd.to_numeric(df['英语听说'], errors='coerce')

                # 获取有效的英语听说成绩数量（>0的成绩）
                valid_speaking = df['英语听说'] > 0
                valid_speaking_count = valid_speaking.sum()

                # 将有效的英语听说成绩加到英语成绩上
                df.loc[valid_speaking, '英语'] = df.loc[valid_speaking, '英语'] + df.loc[valid_speaking, '英语听说']

                # 记录统计信息
                cleaning_stats['英语听说统计'] = {
                    '有效成绩数': valid_speaking_count,
                    '缺考人数': df['英语听说'].isna().sum(),
                }

                # 删除英语听说列
                df = df.drop('英语听说', axis=1)

            # 转换其他所有成绩列为数值类型
            for subject in self.all_subjects:
                if subject in df.columns:
                    df[subject] = pd.to_numeric(df[subject], errors='coerce')

            # 处理必修科目
            required_missing = {}
            for subject in self.required_subjects:
                missing_count = df[subject].isna().sum()
                if missing_count > 0:
                    required_missing[subject] = missing_count
                    # 必修科目缺考标记为-1
                    df[subject] = df[subject].fillna(-1)

            # 处理选考科目
            optional_missing = {}
            for subject in self.optional_subjects:
                missing_count = df[subject].isna().sum()
                if missing_count > 0:
                    optional_missing[subject] = missing_count
                    # 选考科目未选标记为-2
                    df[subject] = df[subject].fillna(-2)

            # 检查无效成绩（超出范围的成绩）
            invalid_scores = {}
            for subject in self.all_subjects:
                # 英语的有效范围需要考虑听说成绩
                max_score = 150
                invalid_mask = (df[subject] > max_score) | (df[subject] < 0)
                invalid_count = invalid_mask.sum()
                if invalid_count > 0:
                    invalid_scores[subject] = invalid_count
                    # 无效成绩标记为-3
                    df.loc[invalid_mask, subject] = -3

            # 汇总清洗统计
            cleaning_stats.update({
                '必修科目缺考': required_missing,
                '选考科目未选': optional_missing,
                '无效成绩': invalid_scores,
            })

            return {
                'success': True,
                'cleaned_df': df,
                'stats': cleaning_stats
            }

        except Exception as e:
            print(f"数据清洗错误: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    def get_valid_scores_stats(self, df):
        """获取有效成绩的统计信息"""
        stats = {}
        for subject in self.all_subjects:
            valid_scores = df[df[subject] >= 0][subject]
            if not valid_scores.empty:
                stats[subject] = {
                    '有效成绩数': len(valid_scores),
                    '平均分': round(valid_scores.mean(), 2),
                    '最高分': round(valid_scores.max(), 2),
                    '最低分': round(valid_scores.min(), 2)
                }
        return stats