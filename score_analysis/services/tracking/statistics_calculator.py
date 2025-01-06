from typing import List, Dict, Any
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

            # 构建配置字典
            self.subjects_config = {}

            # 定义各学段主科目满分映射
            main_subject_scores = {
                'H': 150,  # 高中主科满分150
                'M': 120,  # 初中主科满分120
                'P': 100  # 小学主科满分100
            }

            # 定义主科目列表
            main_subjects = ['chinese', 'math', 'english']

            for row in cursor.fetchall():
                code, full_score, subject_types, is_required = row
                subject_type = 'REQUIRED' if is_required else 'OPTIONAL'

                # 解析学段列表
                levels = subject_types.split('-')  # 例如：'高中-初中-小学' -> ['高中', '初中', '小学']

                # 映射中文学段到代码
                level_map = {
                    '高中': 'H',
                    '初中': 'M',
                    '小学': 'P'
                }

                # 为每个适用的学段添加配置
                for level_cn in levels:
                    level = level_map.get(level_cn)
                    if not level:
                        continue

                    # 根据学段和科目调整满分
                    if code in main_subjects:
                        adjusted_score = main_subject_scores[level]
                    else:
                        adjusted_score = full_score

                    # 初始化学段
                    if level not in self.subjects_config:
                        self.subjects_config[level] = {}

                    # 如果是高中，需要按学生类型分类
                    if level == 'H':
                        # 为每个学生类型初始化配置
                        for student_type in ['SCIENCE', 'LIBERAL', 'UNKNOWN']:
                            if student_type not in self.subjects_config[level]:
                                self.subjects_config[level][student_type] = {
                                    'subjects': {},
                                    'total': 0
                                }
                            self.subjects_config[level][student_type]['subjects'][code] = {
                                'score': adjusted_score,
                                'type': subject_type
                            }
                            # 更新总分（只计算必考科目）
                            if subject_type == 'REQUIRED':
                                self.subjects_config[level][student_type]['total'] += adjusted_score
                    else:
                        # 初中和小学的处理
                        if 'subjects' not in self.subjects_config[level]:
                            self.subjects_config[level]['subjects'] = {}
                            self.subjects_config[level]['total'] = 0
                        self.subjects_config[level]['subjects'][code] = {
                            'score': adjusted_score,
                            'type': subject_type
                        }
                        # 更新总分（只计算必考科目）
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
                                   student_type: str = 'UNKNOWN',
                                   selected_subjects: List[str] = None) -> Dict[str, float]:
        """计算科目T分（包括总分）
        分数为-3时（未参与考试），T分也设为-3
        """

        def _calculate_group_subject_t_scores(score_list: List[Dict]) -> Dict[str, float]:
            if not score_list:
                return {}

            # 获取科目满分
            full_score = self.get_full_score(school_level, subject, student_type)

            # 提取有效分数（排除-3的情况）
            valid_scores = []
            t_scores = {}
            for s in score_list:
                score_value = float(s.get(subject, -3))

                # 如果分数是-3，直接设置T分为-3
                if score_value == -3:
                    t_scores[s['student_id']] = -3
                    continue

                valid_scores.append((s['student_id'], score_value))

            if not valid_scores:
                return t_scores

            # 计算平均值和标准差（只使用有效分数）
            scores_only = [score for _, score in valid_scores]
            mean = sum(scores_only) / len(scores_only)

            squared_diff_sum = sum((score - mean) ** 2 for score in scores_only)
            std_dev = (squared_diff_sum / len(scores_only)) ** 0.5 if len(scores_only) > 1 else 0

            # 计算T分（对齐到原始分数范围）
            for student_id, score in valid_scores:
                if std_dev == 0:
                    t_score = mean
                else:
                    # 计算标准化的T分（中心值为满分的50%）
                    t_score = ((score - mean) / std_dev * (full_score * 0.2) + (full_score * 0.5))
                    # 限制在0到满分范围内
                    t_score = round(max(0, min(full_score, t_score)), 2)
                t_scores[student_id] = t_score

            return t_scores

        if group_by:
            # 按组计算T分
            groups = {}
            for score in scores:
                group_value = score[group_by]
                if group_value not in groups:
                    groups[group_value] = []
                groups[group_value].append(score)

            # 合并所有组的T分
            t_scores = {}
            for group_scores in groups.values():
                t_scores.update(_calculate_group_subject_t_scores(group_scores))
            return t_scores
        else:
            # 计算总体T分
            return _calculate_group_subject_t_scores(scores)

    def calculate_statistics(self, scores: List[Dict], subject: str,
                             group_by: str = None, school_level: str = 'H',
                             student_type: str = 'UNKNOWN',
                             selected_subjects: List[str] = None) -> Dict:
        """计算统计指标"""

        def _calculate_group_statistics(score_list: List[Dict]) -> Dict:
            if not score_list:
                return {}

            # 提取有效分数
            valid_scores = []
            for s in score_list:
                if subject == 'total':
                    score_value = self.calculate_total_score(s, school_level, student_type, selected_subjects)
                else:
                    score_value = float(s.get(subject, 0)) if s.get(subject) is not None else None

                if score_value is not None:
                    valid_scores.append(score_value)

            if not valid_scores:
                return {}

            # 获取满分
            full_score = self.get_full_score(school_level, subject, student_type)

            # 计算统计指标
            stats = {
                'count': len(valid_scores),
                'max': max(valid_scores),
                'min': min(valid_scores),
                'mean': sum(valid_scores) / len(valid_scores),
                'full_score': full_score
            }

            # 计算标准差
            squared_diff_sum = sum((score - stats['mean']) ** 2 for score in valid_scores)
            stats['std_dev'] = math.sqrt(squared_diff_sum / len(valid_scores)) if len(valid_scores) > 1 else 0

            # 计算中位数
            sorted_scores = sorted(valid_scores)
            mid = len(sorted_scores) // 2
            if len(sorted_scores) % 2 == 0:
                stats['median'] = (sorted_scores[mid - 1] + sorted_scores[mid]) / 2
            else:
                stats['median'] = sorted_scores[mid]

            # 所有数值保留2位小数
            for key, value in stats.items():
                if isinstance(value, (float, Decimal)):
                    stats[key] = round(value, 2)

            return stats

        if group_by:
            # 按组计算统计指标
            groups = {}
            for score in scores:
                group_value = score[group_by]
                if group_value not in groups:
                    groups[group_value] = []
                groups[group_value].append(score)

            # 计算每个组的统计指标
            statistics = {}
            for group_name, group_scores in groups.items():
                statistics[group_name] = _calculate_group_statistics(group_scores)
            return statistics
        else:
            # 计算总体统计指标
            return _calculate_group_statistics(scores)