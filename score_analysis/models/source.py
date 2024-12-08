# score_analysis/models/source.py
from django.db import models
from typing import Dict, List, Optional, Union
from decimal import Decimal
from score_processor.models import ScoreStudentBasic as BaseScoreStudentBasic

class ScoreStudentBasic(BaseScoreStudentBasic):
    """
    扩展ScoreStudentBasic模型，添加分析相关的方法
    """
    class Meta:
        proxy =True  # 这表明这是一个代理模型，不会创建新表


    def get_subject_score(self, subject_id: str) -> Optional[Decimal]:
        """
        获取指定科目成绩
        Args:
            subject_id: 科目ID
        Returns:
            Optional[Decimal]: 科目成绩，如果科目不存在返回None
        """
        subject_mapping = {
            'chinese': self.chinese,
            'math': self.math,
            'english': self.english,
            'physics': self.physics,
            'chemistry': self.chemistry,
            'biology': self.biology,
            'history': self.history,
            'politics': self.politics,
            'geography': self.geography,
            'total': self.total_score
        }
        return subject_mapping.get(subject_id)


    def determine_stream_type(self) -> str:
        """
        判断文理科状态
        Returns:
            str: 理科/文科/未确定
        """
        if self.physics > 0:
            return '理科'
        elif self.history > 0:
            return '文科'
        return '未确定'


    def validate_scores(self) -> List[str]:
        """
        验证成绩有效性
        Returns:
            List[str]: 错误信息列表
        """
        errors: List[str] = []
        subject_limits = {
            'chinese': 150,
            'math': 150,
            'english': 150,
            'physics': 100,
            'chemistry': 100,
            'biology': 100,
            'history': 100,
            'politics': 100,
            'geography': 100
        }

        for subject, limit in subject_limits.items():
            score = getattr(self, subject)
            if score is not None:
                if score < 0 or score > limit:
                    errors.append(f"{subject} 分数超出范围: {score}")

        return errors


    def get_stream_subjects(self) -> List[str]:
        """
        获取该学生需要计算的科目列表
        按3+1+2模式：
        - 3：语数外（统一必考）
        - 1：物理/历史（分科指标）
        - 2：根据分科情况从剩余科目中任选两门

        Returns:
            Dict[str, List[str]]: 按类型分组的科目列表
        """
        result: Dict[str, List[str]] = {
            '统一': ['chinese', 'math', 'english'],
            '分科': [],
            '选考': []
        }

        # 判断分科科目
        """获取该学生需要计算的科目列表"""
        common_subjects = ['chinese', 'math', 'english']

        if self.physics > 0:
            result['分科'].append('physics')
            optional_subjects = []
            for subject in ['chemistry', 'biology', 'politics', 'geography']:
                score = getattr(self, subject)
                if score is not None and score > 0:
                    optional_subjects.append(subject)
            optional_subjects.sort(key=lambda x: getattr(self, x), reverse=True)
            result['选考'].extend(optional_subjects[:2])

        elif self.history > 0:
            result['分科'].append('history')
            optional_subjects = []
            for subject in ['politics', 'geography', 'chemistry', 'biology']:
                score = getattr(self, subject)
                if score is not None and score > 0:
                    optional_subjects.append(subject)
            optional_subjects.sort(key=lambda x: getattr(self, x), reverse=True)
            result['选考'].extend(optional_subjects[:2])

        return result


    def get_all_valid_subjects(self) -> List[str]:
        """
        获取所有需要计算T分的科目列表
        Returns:
            List[str]: 科目列表，包含统一科目、分科科目和选考科目
        """
        subjects = self.get_stream_subjects()
        return subjects['统一'] + subjects['分科'] + subjects['选考']


    def is_scores_complete(self) -> bool:
        """
        检查成绩是否完整
        Returns:
            bool: 所有必要科目是否都有成绩
        """
        required_subjects = self.get_all_valid_subjects()
        return all(getattr(self, subject) is not None for subject in required_subjects)


    @property
    def student_info(self) -> Dict[str, str]:
        """
        获取学生基本信息
        Returns:
            Dict[str, str]: 学生基本信息字典
        """
        return {
            'student_id': self.student_id,
            'student_name': self.student_name,
            'school_name': self.school_name,
            'class_name': self.class_field,
            'district_name': self.district_name,
            'select_type': self.select_type
        }