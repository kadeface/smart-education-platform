# score_analysis/services/region/characteristics.py

"""
区域特征分析服务模块
提供区域特征分析的核心功能，包括：
1. 分析区域学科特征（强势/弱势学科）
2. 分析分数分布特征
3. 生成特征报告
"""

from typing import List, Dict, Any
from django.db import transaction
from collections import defaultdict
from score_analysis.models import RegionCharacteristics, RegionLayerAnalysis
from score_analysis.models.statistics import ExamScoreLines

class RegionCharacteristicsService:
    """区域特征分析服务"""

    def __init__(self):
        self.subjects = ['总分', '语文', '数学', '英语', '物理', '化学', '生物', '历史', '政治', '地理']
        self.distribution_types = ['两极分化', '中间集中', '正态分布']
        self.rank_thresholds = {
            '文科': {
                'excellent': 600,   # 优秀线：前600名
                'pass': 3800       # 合格线：前3800名
            },
            '理科': {
                'excellent': 3000,  # 优秀线：前3000名
                'pass': 9500       # 合格线：前9500名
            }
        }
    @transaction.atomic
    def generate_characteristics(self, exam_id: str, district_name: str,
                                 select_type: str, layer_type: str = 'all') -> bool:
        """
        生成区域特征分析
        Args:
            exam_id: 考试ID
            district_name: 区县名称
            select_type: 文理科类型
            layer_type: 层次类型
        Returns:
            bool: 是否生成成功
        """
        try:
            # 1. 获取分层分析数据
            layer_analyses = RegionLayerAnalysis.objects.filter(
                exam_id=exam_id,
                district_name=district_name,
                select_type=select_type,
                layer_type=layer_type
            )

            if not layer_analyses:
                return False

            # 2. 分析学科特征
            subject_features = self._analyze_subject_features(layer_analyses)

            # 3. 分析分布特征
            distribution_features = self._analyze_distribution_features(layer_analyses)

            # 4. 保存特征分析结果
            RegionCharacteristics.objects.update_or_create(
                exam_id=exam_id,
                district_name=district_name,
                select_type=select_type,
                layer_type=layer_type,
                defaults={
                    'subject_features': subject_features,
                    'distribution_features': distribution_features
                }
            )

            return True

        except Exception as e:
            print(f"Error in generate_characteristics: {str(e)}")
            return False

    def _analyze_subject_features(self, layer_analyses) -> Dict:
        """
        分析学科特征
        Args:
            layer_analyses: 分层分析数据查询集
        Returns:
            Dict: 学科特征数据
        """
        # 按T分排序识别强弱势学科
        subject_stats = []
        for analysis in layer_analyses:
            if analysis.subject != '总分':  # 不包括总分
                subject_stats.append({
                    'subject': analysis.subject,
                    't_score': analysis.district_t_score,
                    'rank': 0,  # 临时占位，后面计算
                    'mean': analysis.district_mean,
                    'excellent_rate': self._calculate_excellent_rate(analysis),
                    'pass_rate': self._calculate_pass_rate(analysis)
                })

        # 按T分排序并计算排名
        subject_stats.sort(key=lambda x: x['t_score'], reverse=True)
        for rank, stat in enumerate(subject_stats, 1):
            stat['rank'] = rank

        # 识别强弱势学科
        strong_subjects = subject_stats[:3]  # 前3名为强势
        weak_subjects = subject_stats[-3:]  # 后3名为弱势

        return {
            'strong_subjects': strong_subjects,
            'weak_subjects': weak_subjects
        }

    def _analyze_distribution_features(self, layer_analyses) -> Dict:
        """
        分析分布特征
        Args:
            layer_analyses: 分层分析数据查询集
        Returns:
            Dict: 分布特征数据
        """
        # 获取总分分析数据
        total_score_analysis = next(
            (a for a in layer_analyses if a.subject == '总分'),
            None
        )

        if not total_score_analysis:
            return {}

        # 判断分布类型
        distribution_type = self._determine_distribution_type(
            mean=total_score_analysis.district_mean,
            std_dev=total_score_analysis.district_std_dev
        )

        return {
            'distribution_type': distribution_type,
            'key_indicators': {
                'mean': total_score_analysis.district_mean,
                'std_dev': total_score_analysis.district_std_dev,
                'max_score': total_score_analysis.district_max,
                'min_score': total_score_analysis.district_min,
                'median': self._calculate_median(total_score_analysis)
            }
        }

    def _determine_distribution_type(self, mean: float, std_dev: float) -> str:
        """
        判断分布类型
        Args:
            mean: 平均分
            std_dev: 标准差
        Returns:
            str: 分布类型
        """
        # 基于标准差判断分布类型
        if std_dev > mean * 0.25:  # 标准差较大
            return '两极分化'
        elif std_dev < mean * 0.15:  # 标准差较小
            return '中间集中'
        else:
            return '正态分布'

    def _calculate_rates_by_total_score(self, analysis) -> Dict:
        """
        基于总分计算优秀和合格的比例界限
        Args:
            analysis: 分析数据
        Returns:
            Dict: 包含优秀线和合格线的学生索引
        """
        try:
            # 1. 获取该考试的分数线
            excellent_line = ExamScoreLines.objects.get(
                exam_id=analysis.exam_id,
                select_type=analysis.select_type,
                line_type='优分层'
            ).score

            pass_line = ExamScoreLines.objects.get(
                exam_id=analysis.exam_id,
                select_type=analysis.select_type,
                line_type='本科层'
            ).score

            # 2. 获取总分达到分数线的学生ID列表
            from score_processor.models import ScoreStudentBasic

            # 优秀学生ID集合
            excellent_students = set(ScoreStudentBasic.objects.filter(
                exam_id=analysis.exam_id,
                district_name=analysis.district_name,
                select_type=analysis.select_type,
                total_score__gte=excellent_line
            ).values_list('student_id', flat=True))

            # 合格学生ID集合
            pass_students = set(ScoreStudentBasic.objects.filter(
                exam_id=analysis.exam_id,
                district_name=analysis.district_name,
                select_type=analysis.select_type,
                total_score__gte=pass_line
            ).values_list('student_id', flat=True))

            return {
                'excellent_students': excellent_students,
                'pass_students': pass_students,
                'excellent_line': excellent_line,
                'pass_line': pass_line
            }

        except ExamScoreLines.DoesNotExist:
            print(f"Score lines not found for exam {analysis.exam_id}")
            return {}
        except Exception as e:
            print(f"Error in calculate_rates_by_total_score: {str(e)}")
            return {}

    def _calculate_subject_rates(self, analysis, subject: str,
                                 rate_data: Dict) -> Dict:
        """
        根据总分确定的优秀/合格学生计算单科分布
        Args:
            analysis: 分析数据
            subject: 科目名称
            rate_data: 包含优秀和合格学生ID的数据
        Returns:
            Dict: 单科分布数据
        """
        try:
            from score_processor.models import ScoreStudentBasic
            field_name = subject.lower()

            # 获取该科目的所有成绩数据
            subject_scores = ScoreStudentBasic.objects.filter(
                exam_id=analysis.exam_id,
                district_name=analysis.district_name,
                select_type=analysis.select_type
            ).values('student_id', field_name)

            # 统计各类别人数
            excellent_count = sum(
                1 for score in subject_scores
                if score['student_id'] in rate_data['excellent_students']
            )

            pass_count = sum(
                1 for score in subject_scores
                if score['student_id'] in rate_data['pass_students']
            )

            total_students = analysis.district_student_count

            return {
                'excellent_count': excellent_count,
                'pass_count': pass_count,
                'excellent_rate': round(excellent_count / total_students * 100, 2),
                'pass_rate': round(pass_count / total_students * 100, 2),
                'distribution': {
                    'excellent': excellent_count,
                    'good': pass_count - excellent_count,  # 合格但非优秀
                    'fail': total_students - pass_count  # 不合格
                },
                'distribution_rate': {
                    'excellent': round(excellent_count / total_students * 100, 2),
                    'good': round((pass_count - excellent_count) / total_students * 100, 2),
                    'fail': round((total_students - pass_count) / total_students * 100, 2)
                }
            }

        except Exception as e:
            print(f"Error in calculate_subject_rates: {str(e)}")
            return {}

    def _analyze_subject_features(self, layer_analyses) -> Dict:
        """分析学科特征"""
        try:
            # 1. 首先获取总分的优秀/合格学生
            total_analysis = next(
                (a for a in layer_analyses if a.subject == '总分'),
                None
            )
            if not total_analysis:
                return {}

            rate_data = self._calculate_rates_by_total_score(total_analysis)
            if not rate_data:
                return {}

            # 2. 分析各科目特征
            subject_stats = []
            for analysis in layer_analyses:
                if analysis.subject != '总分':
                    # 使用总分确定的学生集合计算单科分布
                    rate_stats = self._calculate_subject_rates(
                        analysis,
                        analysis.subject,
                        rate_data
                    )

                    subject_stats.append({
                        'subject': analysis.subject,
                        't_score': analysis.district_t_score,
                        'rank': 0,  # 临时占位，后面计算
                        'mean': analysis.district_mean,
                        'excellent_rate': rate_stats.get('excellent_rate', 0),
                        'pass_rate': rate_stats.get('pass_rate', 0),
                        'distribution': rate_stats.get('distribution', {}),
                        'distribution_rate': rate_stats.get('distribution_rate', {})
                    })

            # 3. 按T分排序并计算排名
            subject_stats.sort(key=lambda x: x['t_score'], reverse=True)
            for rank, stat in enumerate(subject_stats, 1):
                stat['rank'] = rank

            return {
                'strong_subjects': subject_stats[:3],  # 前3名为强势
                'weak_subjects': subject_stats[-3:],  # 后3名为弱势
                'all_subjects': subject_stats,  # 所有科目数据
                'score_lines': {  # 分数线信息
                    'excellent_line': rate_data['excellent_line'],
                    'pass_line': rate_data['pass_line']
                }
            }

        except Exception as e:
            print(f"Error in analyze_subject_features: {str(e)}")
            return {}

    def _get_student_ranks(self, exam_id: str, select_type: str) -> Dict:
        """
        获取学生总分排名数据（使用多级排序规则）
        Args:
            exam_id: 考试ID
            select_type: 文理科类型
        Returns:
            Dict: 包含学生ID和排名的映射
        """
        try:
            from score_processor.models import ScoreStudentBasic

            # 获取所有学生的成绩数据，包括排序所需的所有字段
            students = list(ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            ).values(
                'student_id',
                'total_score',
                'math',
                'chinese'
            ).order_by(
                '-total_score',  # 总分降序
                '-math',  # 数学降序
                '-chinese'  # 语文降序
            ))

            # 生成排名映射
            student_ranks = {}
            current_rank = 1
            prev_scores = None
            same_rank_count = 0

            for student in students:
                # 创建当前学生的成绩元组用于比较
                current_scores = (
                    student['total_score'],
                    student['math'],
                    student['chinese']
                )

                # 比较成绩确定排名
                if prev_scores is not None and current_scores < prev_scores:
                    current_rank += same_rank_count
                    same_rank_count = 1
                else:
                    same_rank_count += 1

                student_ranks[student['student_id']] = current_rank
                prev_scores = current_scores

            return student_ranks

        except Exception as e:
            print(f"Error in get_student_ranks: {str(e)}")
            return {}

    def _calculate_rates_by_rank(self, analysis) -> Dict:
        """
        基于排名计算优秀和合格的学生集合
        Args:
            analysis: 分析数据
        Returns:
            Dict: 包含优秀和合格学生ID的集合
        """
        try:
            # 1. 获取排名阈值
            thresholds = self.rank_thresholds.get(analysis.select_type)
            if not thresholds:
                return {}

            # 2. 获取按多级排序规则排序后的学生排名
            student_ranks = self._get_student_ranks(
                analysis.exam_id,
                analysis.select_type
            )

            # 3. 根据排名确定优秀和合格学生集合
            excellent_students = {
                student_id
                for student_id, rank in student_ranks.items()
                if rank <= thresholds['excellent']
            }

            pass_students = {
                student_id
                for student_id, rank in student_ranks.items()
                if rank <= thresholds['pass']
            }

            # 4. 获取分界线成绩（用于展示）
            from score_processor.models import ScoreStudentBasic

            excellent_boundary = ScoreStudentBasic.objects.filter(
                exam_id=analysis.exam_id,
                select_type=analysis.select_type,
                student_id__in=[
                    sid for sid, rank in student_ranks.items()
                    if rank == thresholds['excellent']
                ]
            ).values('total_score', 'math', 'chinese').first()

            pass_boundary = ScoreStudentBasic.objects.filter(
                exam_id=analysis.exam_id,
                select_type=analysis.select_type,
                student_id__in=[
                    sid for sid, rank in student_ranks.items()
                    if rank == thresholds['pass']
                ]
            ).values('total_score', 'math', 'chinese').first()

            return {
                'excellent_students': excellent_students,
                'pass_students': pass_students,
                'rank_thresholds': thresholds,
                'boundary_scores': {
                    'excellent': excellent_boundary,
                    'pass': pass_boundary
                }
            }

        except Exception as e:
            print(f"Error in calculate_rates_by_rank: {str(e)}")
            return {}

    def get_characteristics(self, exam_id: str, district_name: str,
                            select_type: str, layer_type: str = 'all') -> Dict:
        """
        获取区域特征数据
        Args:
            exam_id: 考试ID
            district_name: 区县名称
            select_type: 文理科类型
            layer_type: 层次类型
        Returns:
            Dict: 特征数据
        """
        try:
            characteristics = RegionCharacteristics.objects.get(
                exam_id=exam_id,
                district_name=district_name,
                select_type=select_type,
                layer_type=layer_type
            )

            return {
                'subject_features': characteristics.subject_features,
                'distribution_features': characteristics.distribution_features
            }

        except RegionCharacteristics.DoesNotExist:
            return {}
        except Exception as e:
            print(f"Error in get_characteristics: {str(e)}")
            return {}