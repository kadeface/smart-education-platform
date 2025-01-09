from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import numpy as np
from django.db.models import Q, Count, Avg, Max

from score_analysis.models import BaseExamConfig, ScoreStudentBasic
from score_analysis.models.statistics import ExamLevelStatistics, ExamLevelAnalysisTask, ExamLevelAnalysisConfig
import logging
logger = logging.getLogger(__name__)


@dataclass
class ExamOverview:
    """考试概况数据"""
    school_count: int
    student_count: int
    mean_score: float
    max_score: float
    top_school: str
    score_lines: Dict[str, Dict[str, Any]]  # 各分数线及达线情况


@dataclass
class ScoreLineDistribution:
    """分数线分布数据"""
    lines: Dict[str, float]  # 各分数线
    counts: Dict[str, int]  # 达线人数
    rates: Dict[str, float]  # 达线比例


@dataclass
class RankingDistribution:
    """排名分布数据"""
    rank_ranges: List[int]  # [10, 20, 50, 100, 200, 500]
    school_counts: Dict[str, Dict[str, int]]  # 学校在各排名段的人数


@dataclass
class SubjectQuartiles:
    """学科四分位数据"""
    subjects: List[str]
    mean_scores: Dict[str, float]
    max_scores: Dict[str, float]
    quartile_80: Dict[str, float]
    median_scores: Dict[str, float]
    quartile_20: Dict[str, float]
    min_scores: Dict[str, float]


@dataclass
class SchoolAverages:
    """学校平均分数据"""
    schools: List[str]
    total_scores: Dict[str, float]
    subject_scores: Dict[str, Dict[str, float]]
    rankings: Dict[str, int]


class ExamLevelAnalysisGenerator:
    """统计数据生成器"""

    def __init__(self, exam_id: str, select_type: str):
        self.exam_id = exam_id
        self.select_type = select_type
        self.config = self._load_config()
        self.scores_data = None

    def _load_config(self) -> ExamLevelAnalysisConfig:
        """加载考试配置"""
        return ExamLevelAnalysisConfig.objects.get(
            exam_id=self.exam_id,
            select_type=self.select_type,
            is_active=True
        )

    def set_scores_data(self, scores_data: Dict[str, Dict[str, List[float]]]):
        """设置成绩数据

        Args:
            scores_data: {
                'total': {'学校A': [总分列表], '学校B': [总分列表]},
                '语文': {'学校A': [分数列表], '学校B': [分数列表]},
                ...
            }
        """
        self.scores_data = scores_data

    def _is_divided(self, exam_id: str) -> bool:
        """
        判断是否为分科考试
        Args:
            exam_id: 考试ID
        Returns:
            bool: 是否分科
        """
        try:
            # 获取考试配置
            exam = BaseExamConfig.objects.get(exam_id=exam_id)

            # 判断学期
            divided_semesters = ['高一下', '高二上', '高二下', '高三上', '高三下']
            return exam.semester in divided_semesters

        except Exception as e:
            logger.error(f"判断分科状态失败: {str(e)}")
            return False

    def generate_exam_overview(self, exam_id: str, select_type: str) -> ExamOverview:
        """生成考试概况"""
        scores = ScoreStudentBasic.objects.filter(
            exam_id=exam_id,
            select_type=select_type
        )

        if not scores.exists():
            raise ValueError(f"未找到 {exam_id} 的 {select_type} 成绩数据")

        # 使用聚合函数获取基础统计
        overview_stats = scores.aggregate(
            school_count=Count('school_name', distinct=True),
            student_count=Count('id'),
            mean_score=Avg('total_score'),
            max_score=Max('total_score')
        )

        # 获取最高分所属学校
        top_score_record = scores.order_by('-total_score').first()

        # 计算分数线达线情况
        config = ExamLevelAnalysisConfig.objects.get(
            exam_id=exam_id,
            select_type=select_type,
            is_active=True
        )

        score_lines = {}
        total_count = overview_stats['student_count']

        # 使用 _is_divided 判断是否为分科考试
        if self._is_divided(exam_id):
            # 分科考试：使用固定分数线
            for line_name, line_score in config.score_lines.items():
                count = scores.filter(total_score__gte=line_score).count()
                score_lines[line_name] = {
                    'line': line_score,
                    'count': count,
                    'rate': round(count / total_count * 100, 2)
                }
        else:
            # 未分科考试：按比例计算
            ordered_scores = list(
                scores.values_list('total_score', flat=True)
                .order_by('-total_score')
            )
            for line_name, ratio in config.score_lines.items():
                index = int(total_count * ratio)
                if index > 0 and index < len(ordered_scores):
                    line_score = ordered_scores[index - 1]
                    count = scores.filter(total_score__gte=line_score).count()
                    score_lines[line_name] = {
                        'line': float(line_score),
                        'count': count,
                        'rate': round(count / total_count * 100, 2)
                    }

        return ExamOverview(
            school_count=overview_stats['school_count'],
            student_count=overview_stats['student_count'],
            mean_score=round(float(overview_stats['mean_score']), 2),
            max_score=float(overview_stats['max_score']),
            top_school=top_score_record.school_name if top_score_record else '',
            score_lines=score_lines
        )

    def generate_score_line_distribution(self) -> ScoreLineDistribution:
        """生成分数线分布"""
        if not self.scores_data:
            raise ValueError("请先设置成绩数据")

        all_scores = [
            score for scores in self.scores_data['total'].values()
            for score in scores
        ]

        lines = {}
        counts = {}
        rates = {}

        if self.select_type in ['文科', '理科']:
            for line_name, line_score in self.config.score_lines.items():
                lines[line_name] = line_score
                count = sum(1 for score in all_scores if score >= line_score)
                counts[line_name] = count
                rates[line_name] = round(count / len(all_scores) * 100, 2)
        else:
            # 未分科按比例计算
            sorted_scores = sorted(all_scores, reverse=True)
            for line_name, ratio in self.config.score_lines.items():
                index = int(len(all_scores) * ratio)
                if index > 0:
                    line_score = sorted_scores[index - 1]
                    lines[line_name] = line_score
                    count = sum(1 for score in all_scores if score >= line_score)
                    counts[line_name] = count
                    rates[line_name] = round(count / len(all_scores) * 100, 2)

        return ScoreLineDistribution(
            lines=lines,
            counts=counts,
            rates=rates
        )

    def generate_ranking_distribution(self) -> RankingDistribution:
        """生成排名分布"""
        if not self.scores_data:
            raise ValueError("请先设置成绩数据")

        # 获取市级排名范围
        rank_ranges = self.config.rank_ranges.get('市级', [])

        # 计算总体排名
        all_scores = [
            score for scores in self.scores_data['total'].values()
            for score in scores
        ]
        sorted_scores = sorted(all_scores, reverse=True)

        # 计算各学校在不同排名段的人数
        school_counts = {}
        for rank in rank_ranges:
            if rank <= len(sorted_scores):
                cutoff = sorted_scores[rank - 1]
                counts = {}
                for school, scores in self.scores_data['total'].items():
                    count = sum(1 for score in scores if score >= cutoff)
                    if count > 0:
                        counts[school] = count
                school_counts[f'TOP{rank}'] = counts

        return RankingDistribution(
            rank_ranges=rank_ranges,
            school_counts=school_counts
        )

    def generate_subject_quartiles(self) -> SubjectQuartiles:
        """生成学科四分位数据"""
        if not self.scores_data:
            raise ValueError("请先设置成绩数据")

        # 获取所有科目（除总分外）
        subjects = [subj for subj in self.scores_data.keys() if subj != 'total']

        # 初始化结果字典
        mean_scores = {}
        max_scores = {}
        quartile_80 = {}
        median_scores = {}
        quartile_20 = {}
        min_scores = {}

        # 计算总分的统计数据
        total_scores = [
            score for scores in self.scores_data['total'].values()
            for score in scores
        ]
        mean_scores['total'] = round(np.mean(total_scores), 2)
        max_scores['total'] = max(total_scores)
        quartile_80['total'] = round(np.percentile(total_scores, 80), 2)
        median_scores['total'] = round(np.median(total_scores), 2)
        quartile_20['total'] = round(np.percentile(total_scores, 20), 2)
        min_scores['total'] = min(total_scores)

        # 计算各科目的统计数据
        for subject in subjects:
            subject_scores = [
                score for scores in self.scores_data[subject].values()
                for score in scores
            ]
            mean_scores[subject] = round(np.mean(subject_scores), 2)
            max_scores[subject] = max(subject_scores)
            quartile_80[subject] = round(np.percentile(subject_scores, 80), 2)
            median_scores[subject] = round(np.median(subject_scores), 2)
            quartile_20[subject] = round(np.percentile(subject_scores, 20), 2)
            min_scores[subject] = min(subject_scores)

        return SubjectQuartiles(
            subjects=['total'] + subjects,
            mean_scores=mean_scores,
            max_scores=max_scores,
            quartile_80=quartile_80,
            median_scores=median_scores,
            quartile_20=quartile_20,
            min_scores=min_scores
        )

    def generate_school_averages(self) -> SchoolAverages:
        """生成学校平均分数据"""
        if not self.scores_data:
            raise ValueError("请先设置成绩数据")

        schools = list(self.scores_data['total'].keys())
        subjects = [subj for subj in self.scores_data.keys() if subj != 'total']

        # 计算总分平均分
        total_scores = {}
        for school in schools:
            scores = self.scores_data['total'][school]
            total_scores[school] = round(np.mean(scores), 2)

        # 计算各科目平均分
        subject_scores = {}
        for subject in subjects:
            subject_scores[subject] = {}
            for school in schools:
                scores = self.scores_data[subject][school]
                subject_scores[subject][school] = round(np.mean(scores), 2)

        # 计算总分排名
        rankings = dict(
            zip(
                sorted(schools, key=lambda x: total_scores[x], reverse=True),
                range(1, len(schools) + 1)
            )
        )

        return SchoolAverages(
            schools=schools,
            total_scores=total_scores,
            subject_scores=subject_scores,
            rankings=rankings
        )

    def generate_all_statistics(self) -> Dict[str, Any]:
        """生成所有统计数据"""
        return {
            'overview': self.generate_exam_overview(),
            'score_line_dist': self.generate_score_line_distribution(),
            'ranking_dist': self.generate_ranking_distribution(),
            'subject_quartiles': self.generate_subject_quartiles(),
            'school_averages': self.generate_school_averages()
        }