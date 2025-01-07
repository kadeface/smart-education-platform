import logging
from typing import List, Dict
from decimal import Decimal
import math
from enum import Enum
from django.db import connection


class StudentType(Enum):
    UNKNOWN = 'UNKNOWN'  # 未分科
    SCIENCE = 'SCIENCE'  # 理科
    LIBERAL = 'LIBERAL'  # 文科


class SubjectType(Enum):
    REQUIRED = 'REQUIRED'  # 必考
    OPTIONAL = 'OPTIONAL'  # 选考


class StatisticsCalculator:
    # 定义各学段科目和满分标准
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._load_subject_config()

    def _load_subject_config(self):
        """从数据库加载科目配置"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    subject_id as code,
                    full_score,
                    subject_type,
                    is_required
                FROM base_subject_config
            """)

            # 定义各学段主科目满分映射
            main_subject_scores = {
                'H': 150,  # 高中主科满分150
                'M': 120,  # 初中主科满分120
                'P': 100  # 小学主科满分100
            }

            # 定义主科目列表
            main_subjects = ['chinese', 'math', 'english']

            # 构建配置字典
            self.subjects_config = {
                'P': {'subjects': {}, 'total': 0},
                'M': {'subjects': {}, 'total': 0},
                'H': {
                    'ALL': {'subjects': {}, 'total': 0},
                    'SCIENCE': {'subjects': {}, 'total': 0},
                    'LIBERAL': {'subjects': {}, 'total': 0},
                    'UNKNOWN': {'subjects': {}, 'total': 0}
                }
            }

            for row in cursor.fetchall():
                code, full_score, subject_types, is_required = row
                subject_type = 'REQUIRED' if is_required else 'OPTIONAL'

                # 解析学段列表
                levels = []
                if '小学' in subject_types:
                    levels.append('P')
                if '初中' in subject_types:
                    levels.append('M')
                if '高中' in subject_types:
                    levels.append('H')

                for level in levels:
                    # 根据学段和科目调整满分
                    adjusted_score = main_subject_scores[level] if code in main_subjects else full_score

                    if level == 'H':
                        for student_type in ['ALL', 'SCIENCE', 'LIBERAL', 'UNKNOWN']:
                            self.subjects_config[level][student_type]['subjects'][code] = {
                                'score': adjusted_score,
                                'type': subject_type
                            }
                            if subject_type == 'REQUIRED':
                                self.subjects_config[level][student_type]['total'] += adjusted_score
                    else:
                        self.subjects_config[level]['subjects'][code] = {
                            'score': adjusted_score,
                            'type': subject_type
                        }
                        if subject_type == 'REQUIRED':
                            self.subjects_config[level]['total'] += adjusted_score

    def get_student_optional_subjects(self, student_id: int, semester: str) -> List[str]:
        """获取学生的选考科目"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT sos.subject_id
                FROM student_optional_subjects sos
                JOIN base_subject_config bsc ON sos.subject_id = bsc.subject_id
                WHERE sos.student_id = %s AND sos.semester = %s
            """, [student_id, semester])
            return [row[0] for row in cursor.fetchall()]

    def get_subjects(self, school_level: str, student_type: str = 'UNKNOWN',
                     include_optional: bool = True) -> List[str]:
        """获取指定学段和类型的科目列表"""
        if school_level == 'H':
            subjects_config = self.subjects_config[school_level][student_type]['subjects']
        else:
            subjects_config = self.subjects_config[school_level]['subjects']

        if include_optional:
            return list(subjects_config.keys())
        else:
            return [subject for subject, config in subjects_config.items()
                    if config['type'] == 'REQUIRED']

    def get_optional_subjects(self, school_level: str, student_type: str) -> List[str]:
        """获取选考科目列表

        Args:
            school_level: 学段 ('H'/'M'/'P')
            student_type: 学生类型 ('SCIENCE'/'LIBERAL'/'UNKNOWN')

        Returns:
            List[str]: 选考科目列表
        """
        if school_level != 'H' or student_type == 'UNKNOWN':
            return []

        subjects_config = self.subjects_config[school_level][student_type]['subjects']
        return [subject for subject, config in subjects_config.items()
                if config['type'] == 'OPTIONAL']

    def calculate_total_score(self, score: Dict, school_level: str,
                              student_type: str = 'UNKNOWN',
                              selected_subjects: List[str] = None) -> float:
        """获取总分

        现在总分直接从数据中读取，不需要计算
        保留此方法是为了兼容性，以及处理特殊情况
        """
        # 优先使用已有的总分
        if 'total_score' in score and score['total_score'] is not None:
            return float(score['total_score'])

        # 如果没有总分，才进行计算（作为备选方案）
        # 获取必考科目
        required_subjects = self.get_subjects(school_level, student_type, include_optional=False)

        # 计算必考科目总分
        total = sum(
            float(score.get(subject, 0))
            for subject in required_subjects
            if score.get(subject) is not None
        )

        # 如果是高中且已分科，添加选考科目分数
        if school_level == 'H' and student_type != 'UNKNOWN' and selected_subjects:
            # 确保只计算两门选考科目
            valid_optional = [s for s in selected_subjects if
                              s in self.get_optional_subjects(school_level, student_type)]
            valid_optional = valid_optional[:2]  # 只取前两门

            # 添加选考科目分数
            total += sum(
                float(score.get(subject, 0))
                for subject in valid_optional
                if score.get(subject) is not None
            )

        return round(total, 2)

    def get_full_score(self, school_level: str, subject: str,
                       student_type: str = 'UNKNOWN') -> int:
        """获取满分"""
        if school_level == 'H':
            return self.subjects_config[school_level][student_type]['subjects'][subject]['score']
        return self.subjects_config[school_level]['subjects'][subject]['score']

    def calculate_subject_t_scores(self, scores: List[Dict], subject: str,
                                   group_by: str = None, school_level: str = 'H',
                                   student_type: str = 'UNKNOWN') -> Dict[str, float]:
        """计算科目T分"""
        if not scores:
            return {}

        def _calculate_group_t_scores(score_list: List[Dict]) -> Dict[str, float]:
            if not score_list:
                return {}

            try:
                # 获取科目满分
                full_score = self.get_full_score(school_level, subject, student_type)

                # 提取有效分数
                valid_scores = []
                t_scores = {}

                # 使用列表推导式优化，添加错误处理
                invalid_scores = {}
                valid_scores = []

                for s in score_list:
                    try:
                        student_id = s.get('student_id')
                        if not student_id:
                            continue

                        score_value = float(s.get(subject, -3))
                        if score_value == -3:
                            invalid_scores[student_id] = -3
                        else:
                            valid_scores.append((student_id, score_value))
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"处理学生成绩时出错: {str(e)}, 数据: {s}")
                        continue

                if not valid_scores:
                    return invalid_scores

                # 使用numpy优化计算（如果可用）
                try:
                    import numpy as np
                    scores_array = np.array([score for _, score in valid_scores])
                    mean = np.mean(scores_array)
                    std_dev = np.std(scores_array) if len(scores_array) > 1 else 0
                except ImportError:
                    scores_only = [score for _, score in valid_scores]
                    mean = sum(scores_only) / len(scores_only)
                    squared_diff_sum = sum((score - mean) ** 2 for score in scores_only)
                    std_dev = (squared_diff_sum / len(scores_only)) ** 0.5 if len(scores_only) > 1 else 0
                except Exception as e:
                    self.logger.error(f"计算平均值和标准差时出错: {str(e)}")
                    return invalid_scores

                # 计算T分
                t_scores = invalid_scores.copy()
                for student_id, score in valid_scores:
                    try:
                        if std_dev == 0:
                            t_score = mean
                        else:
                            t_score = ((score - mean) / std_dev * (full_score * 0.2) + (full_score * 0.5))
                            t_score = round(max(0, min(full_score, t_score)), 2)
                        t_scores[student_id] = t_score
                    except Exception as e:
                        self.logger.error(f"计算学生 {student_id} 的T分时出错: {str(e)}")
                        t_scores[student_id] = 0

                return t_scores

            except Exception as e:
                self.logger.error(f"计算分组T分时出错: {str(e)}")
                return {}

        try:
            if group_by:
                # 使用字典推导式优化分组，添加错误处理
                groups = {}
                for score in scores:
                    try:
                        group_value = score.get(group_by)
                        if group_value is not None:
                            groups.setdefault(group_value, []).append(score)
                    except Exception as e:
                        self.logger.warning(f"处理分组数据时出错: {str(e)}, 数据: {score}")
                        continue

                # 合并所有组的T分
                all_t_scores = {}
                for group_scores in groups.values():
                    all_t_scores.update(_calculate_group_t_scores(group_scores))
                return all_t_scores
            else:
                return _calculate_group_t_scores(scores)

        except Exception as e:
            self.logger.error(f"计算T分时出错: {str(e)}")
            return {}

    def calculate_statistics(self, scores: List[Dict], subject: str,
                             group_by: str = None, school_level: str = 'H',
                             student_type: str = 'UNKNOWN') -> Dict:
        """计算统计指标"""

        def _calculate_group_statistics(score_list: List[Dict]) -> Dict:
            if not score_list:
                return {}

            # 提取有效分数
            valid_scores = []
            if subject == 'total':
                valid_scores = [self.calculate_total_score(s, school_level, student_type)
                                for s in score_list if s.get('total_score') is not None]
            else:
                valid_scores = [float(s.get(subject, 0))
                                for s in score_list if s.get(subject) is not None]

            if not valid_scores:
                return {}

            # 使用numpy优化计算（如果可用）
            try:
                import numpy as np
                scores_array = np.array(valid_scores)
                stats = {
                    'count': len(scores_array),
                    'max': float(np.max(scores_array)),
                    'min': float(np.min(scores_array)),
                    'mean': float(np.mean(scores_array)),
                    'median': float(np.median(scores_array)),
                    'std_dev': float(np.std(scores_array)) if len(scores_array) > 1 else 0,
                    'full_score': self.get_full_score(school_level, subject, student_type)
                }
            except ImportError:
                # 降级为普通计算
                stats = {
                    'count': len(valid_scores),
                    'max': max(valid_scores),
                    'min': min(valid_scores),
                    'mean': sum(valid_scores) / len(valid_scores),
                    'full_score': self.get_full_score(school_level, subject, student_type)
                }

                # 计算标准差
                squared_diff_sum = sum((score - stats['mean']) ** 2 for score in valid_scores)
                stats['std_dev'] = math.sqrt(squared_diff_sum / len(valid_scores)) if len(valid_scores) > 1 else 0

                # 计算中位数
                sorted_scores = sorted(valid_scores)
                mid = len(sorted_scores) // 2
                stats['median'] = (sorted_scores[mid - 1] + sorted_scores[mid]) / 2 if len(sorted_scores) % 2 == 0 else \
                sorted_scores[mid]

            return {k: round(v, 2) if isinstance(v, (float, Decimal)) else v
                    for k, v in stats.items()}

        if group_by:
            # 使用字典推导式优化分组
            groups = {}
            for score in scores:
                group_value = score[group_by]
                groups.setdefault(group_value, []).append(score)

            return {group_name: _calculate_group_statistics(group_scores)
                    for group_name, group_scores in groups.items()}
        else:
            return _calculate_group_statistics(scores)