from typing import List, Dict, Any, Tuple
from decimal import Decimal

class RankingCalculator:
    def __init__(self, statistics_calculator):
        self.statistics_calculator = statistics_calculator

    def calculate_total_rank(self, scores: List[Dict], group_by: str = None,
                           student_type: str = 'UNKNOWN') -> Dict[str, int]:
        """计算总分排名"""
        def _sort_key(score: Dict) -> Tuple:
            return (
                float(score['total_score']),
                float(score['math']),
                float(score['chinese'])
            )

        if group_by:
            groups = {}
            for score in scores:
                group_value = score[group_by]
                if group_value not in groups:
                    groups[group_value] = []
                groups[group_value].append(score)

            ranks = {}
            for group_scores in groups.values():
                sorted_scores = sorted(group_scores, key=_sort_key, reverse=True)
                ranks.update(self._calculate_ranks(sorted_scores, _sort_key))
            return ranks
        else:
            sorted_scores = sorted(scores, key=_sort_key, reverse=True)
            return self._calculate_ranks(sorted_scores, _sort_key)

    def calculate_subject_rank(self, scores: List[Dict], subject: str,
                             group_by: str = None, student_type: str = 'UNKNOWN',
                             school_level: str = 'H') -> Dict[str, int]:
        """计算单科排名
        排名规则：
        - 数学：数学 -> 总分 -> 语文
        - 其他科目：该科目 -> 总分 -> 数学
        - 选考科目：只对选择了该科目的学生排名（分数不为-3的学生）
        """
        def _sort_key(score: Dict) -> Tuple:
            # 高中选考科目特殊处理
            if school_level == 'H' and subject in ['chemistry', 'biology', 'politics', 'geography']:
                # 检查是否为选考科目
                if student_type != 'UNKNOWN':
                    score_value = float(score.get(subject, -3))
                    if score_value == -3:  # 未选考的学生
                        return (float('-inf'),)

            # 数学排名规则
            if subject == 'math':
                return (
                    float(score.get(subject, 0)),
                    float(score.get('total_score', 0)),
                    float(score.get('chinese', 0))
                )
            # 其他科目排名规则
            else:
                return (
                    float(score.get(subject, 0)),
                    float(score.get('total_score', 0)),
                    float(score.get('math', 0))
                )

        # 过滤出有效的成绩（针对选考科目）
        valid_scores = []
        for score in scores:
            # 高中选考科目特殊处理
            if school_level == 'H' and subject in ['chemistry', 'biology', 'politics', 'geography']:
                if student_type != 'UNKNOWN':
                    score_value = float(score.get(subject, -3))
                    if score_value == -3:  # 跳过未选考的学生
                        continue
            valid_scores.append(score)

        if group_by:
            groups = {}
            for score in valid_scores:
                group_value = score[group_by]
                if group_value not in groups:
                    groups[group_value] = []
                groups[group_value].append(score)

            ranks = {}
            for group_scores in groups.values():
                sorted_scores = sorted(group_scores, key=_sort_key, reverse=True)
                ranks.update(self._calculate_ranks(sorted_scores, _sort_key))
            return ranks
        else:
            sorted_scores = sorted(valid_scores, key=_sort_key, reverse=True)
            return self._calculate_ranks(sorted_scores, _sort_key)

    def _calculate_ranks(self, sorted_scores: List[Dict], key_func) -> Dict[str, int]:
        """通用排名计算逻辑"""
        ranks = {}
        current_rank = 1
        same_rank_count = 1
        prev_key = None

        for score in sorted_scores:
            current_key = key_func(score)
            if prev_key and current_key == prev_key:
                # 相同分数，排名相同
                ranks[score['student_id']] = ranks[prev_student_id]
                same_rank_count += 1
            else:
                # 不同分数，排名为当前位置
                ranks[score['student_id']] = current_rank
                current_rank += same_rank_count
                same_rank_count = 1
            prev_key = current_key
            prev_student_id = score['student_id']

        return ranks