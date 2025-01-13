from typing import List, Dict, Tuple, Callable, Optional
from functools import lru_cache
import logging
from score_processor.models import BaseExamConfig

class RankingCalculator:
    """排名计算服务类"""

    def __init__(self, statistics_calculator):
        self.statistics_calculator = statistics_calculator
        self.logger = logging.getLogger(__name__)

    @lru_cache(maxsize=128)
    def _get_sort_key_function(self, subject: str) -> Callable[[Dict], Tuple]:
        """获取排序键函数（使用缓存优化）"""
        if subject == 'math':
            return lambda score: (
                float(score.get('math', 0)),
                float(score.get('total_score', 0)),
                float(score.get('chinese', 0))
            )
        elif subject == 'total_score':
            return lambda score: (
                float(score.get('total_score', 0)),
                float(score.get('math', 0)),
                float(score.get('chinese', 0))
            )
        else:
            return lambda score: (
                float(score.get(subject, 0)),
                float(score.get('total_score', 0)),
                float(score.get('math', 0))
            )

    def _filter_valid_scores(self, scores: List[Dict], subject: str,
                           is_stream_divided: bool) -> List[Dict]:
        """筛选有效成绩"""
        if not is_stream_divided:
            return scores

        return [
            score for score in scores
            if (score.get('select_type') in ['文科', '理科']) and
               (subject not in ['chemistry', 'biology', 'politics', 'geography'] or
                float(score.get(subject, -3)) != -3)
        ]

    def calculate_total_rank(self, scores: List[Dict], group_by: str = None,
                           student_type: str = 'ALL') -> Dict[str, int]:
        """计算总分排名"""
        if not scores:
            return {}

        exam_id = scores[0].get('exam_id')
        is_stream_divided = self._check_stream_divided(exam_id)
        sort_key = self._get_sort_key_function('total_score')

        # 如果不分科或指定了student_type，直接计算
        if not is_stream_divided or student_type != 'ALL':
            valid_scores = [s for s in scores if student_type == 'ALL' or
                          s.get('select_type') == student_type]
            return self._calculate_group_ranks(valid_scores, group_by, sort_key)

        # 分科情况：按文理分别计算
        stream_groups = {
            '理科': [s for s in scores if s.get('select_type') == '理科'],
            '文科': [s for s in scores if s.get('select_type') == '文科']
        }

        return {
            student_id: rank
            for stream_scores in stream_groups.values()
            for student_id, rank in self._calculate_group_ranks(
                stream_scores, group_by, sort_key
            ).items()
        }

    def calculate_subject_rank(self, scores: List[Dict], subject: str,
                             group_by: str = None, student_type: str = 'ALL') -> Dict[str, int]:
        """计算单科排名"""
        if not scores:
            return {}

        exam_id = scores[0].get('exam_id')
        is_stream_divided = self._check_stream_divided(exam_id)
        sort_key = self._get_sort_key_function(subject)

        # 筛选有效成绩
        valid_scores = self._filter_valid_scores(scores, subject, is_stream_divided)

        # 如果不分科或指定了student_type，直接计算
        if not is_stream_divided or student_type != 'ALL':
            filtered_scores = [s for s in valid_scores if student_type == 'ALL' or
                             s.get('select_type') == student_type]
            return self._calculate_group_ranks(filtered_scores, group_by, sort_key)

        # 分科情况：按文理分别计算
        stream_groups = {
            '理科': [s for s in valid_scores if s.get('select_type') == '理科'],
            '文科': [s for s in valid_scores if s.get('select_type') == '文科']
        }

        return {
            student_id: rank
            for stream_scores in stream_groups.values()
            for student_id, rank in self._calculate_group_ranks(
                stream_scores, group_by, sort_key
            ).items()
        }

    def _calculate_group_ranks(self, scores: List[Dict], group_by: Optional[str],
                             sort_key: Callable) -> Dict[str, int]:
        """计算分组排名"""
        if not scores:
            return {}

        if group_by:
            # 使用字典推导式优化分组
            groups = {}
            for score in scores:
                groups.setdefault(score[group_by], []).append(score)

            return {
                student_id: rank
                for group_scores in groups.values()
                for student_id, rank in self._calculate_ranks(
                    sorted(group_scores, key=sort_key, reverse=True),
                    sort_key
                ).items()
            }

        return self._calculate_ranks(
            sorted(scores, key=sort_key, reverse=True),
            sort_key
        )

    def _calculate_ranks(self, sorted_scores: List[Dict], key_func: Callable) -> Dict[str, int]:
        """通用排名计算逻辑"""
        if not sorted_scores:
            return {}

        try:
            ranks = {}
            current_rank = 1
            same_rank_count = 1

            # 安全获取第一个分数
            first_score = sorted_scores[0]
            if not isinstance(first_score, dict) or 'student_id' not in first_score:
                self.logger.error("Invalid score data format")
                return {}

            prev_key = key_func(first_score)
            prev_student_id = first_score['student_id']
            ranks[prev_student_id] = current_rank

            for score in sorted_scores[1:]:
                if not isinstance(score, dict) or 'student_id' not in score:
                    continue

                try:
                    current_key = key_func(score)
                    student_id = score['student_id']
                except Exception as e:
                    self.logger.error(f"Error processing score: {str(e)}")
                    continue

                if current_key == prev_key:
                    ranks[student_id] = current_rank
                    same_rank_count += 1
                else:
                    current_rank += same_rank_count
                    ranks[student_id] = current_rank
                    same_rank_count = 1
                    prev_key = current_key

            return ranks

        except Exception as e:
            self.logger.error(f"计算排名时出错: {str(e)}")
            return {}

    @lru_cache(maxsize=128)
    def _check_stream_divided(self, exam_id: str) -> bool:
        """检查考试是否分科（使用缓存优化）"""
        try:
            exam_config = BaseExamConfig.objects.get(exam_id=exam_id)
            school_level = exam_id.split('-')[2]

            return (school_level == 'H' and
                    exam_config.semester != 'H1-1')

        except Exception as e:
            self.logger.error(f"检查考试分科状态时出错: {str(e)}")
            return False