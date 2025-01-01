import json
from typing import List, Dict
from django.db import transaction, connection
from .statistics_calculator import StatisticsCalculator
from .ranking_calculator import RankingCalculator


class TrackingGenerator:
    def __init__(self):
        self.stats_calculator = StatisticsCalculator()
        self.rank_calculator = RankingCalculator(self.stats_calculator)

    def generate(self, exam_id: str, generate_t_score: bool = True, generate_rank: bool = True):
        """生成发展跟踪数据"""
        try:
            with transaction.atomic():
                # 1. 获取考试数据
                scores = self._get_exam_scores(exam_id)
                if not scores:
                    raise ValueError(f"未找到考试 {exam_id} 的成绩数据")

                # 2. 获取考试基本信息
                exam_info = self._get_exam_info(exam_id)

                # 3. 生成T分
                t_scores = {}
                if generate_t_score:
                    t_scores = self._generate_t_scores(scores, exam_info)

                # 4. 生成排名
                ranks = {}
                if generate_rank:
                    ranks = self._generate_ranks(scores, exam_info)

                # 5. 保存数据
                self._save_tracking_data(exam_id, scores, t_scores, ranks)

        except Exception as e:
            raise Exception(f"生成发展跟踪数据失败: {str(e)}")

    def _get_exam_scores(self, exam_id: str) -> list:
        """获取考试成绩数据"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    student_id,
                    chinese,
                    math,
                    english,
                    physics,
                    chemistry,
                    biology,
                    politics,
                    history,
                    geography,
                    total_score,
                    select_type,
                    school_name,
                    district_name,
                    class
                FROM score_student_basic
                WHERE exam_id = %s
            """, [exam_id])
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _get_exam_info(self, exam_id: str) -> dict:
        """获取考试信息"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    semester,
                    exam_type,
                    status,
                    grade_level
                FROM base_exam_config
                WHERE exam_id = %s
            """, [exam_id])
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"未找到考试 {exam_id} 的配置信息")
            return {
                'semester': row[0],
                'exam_type': row[1],
                'status': row[2],
                'grade_level': row[3]
            }

    def _generate_t_scores(self, scores: list, exam_info: dict) -> dict:
        """生成T分
        当select_type不是'未分科'时，按文理分类分别计算T分
        """
        t_scores = {}
        subjects = ['chinese', 'math', 'english', 'physics', 'chemistry',
                    'biology', 'politics', 'history', 'geography', 'total_score']

        # 按文理分组
        science_scores = [s for s in scores if s['select_type'] == '理科']
        liberal_scores = [s for s in scores if s['select_type'] == '文科']
        undecided_scores = [s for s in scores if s['select_type'] == '未分科']

        # 如果有已分科的学生，只按科类分别计算
        if science_scores or liberal_scores:
            # 理科学生T分
            if science_scores:
                for subject in subjects:
                    # 理科学生的物理是必考，历史不参与计算
                    if subject == 'history':
                        continue
                    subject_t_scores = self.stats_calculator.calculate_subject_t_scores(
                        scores=science_scores,
                        subject=subject,
                        school_level='H',
                        student_type='SCIENCE'
                    )
                    if subject not in t_scores:
                        t_scores[subject] = {}
                    t_scores[subject].update(subject_t_scores)

            # 文科学生T分
            if liberal_scores:
                for subject in subjects:
                    # 文科学生的历史是必考，物理不参与计算
                    if subject == 'physics':
                        continue
                    subject_t_scores = self.stats_calculator.calculate_subject_t_scores(
                        scores=liberal_scores,
                        subject=subject,
                        school_level='H',
                        student_type='LIBERAL'
                    )
                    if subject not in t_scores:
                        t_scores[subject] = {}
                    t_scores[subject].update(subject_t_scores)

        # 未分科的学生单独计算
        if undecided_scores:
            for subject in subjects:
                subject_t_scores = self.stats_calculator.calculate_subject_t_scores(
                    scores=undecided_scores,
                    subject=subject,
                    school_level='H',
                    student_type='UNKNOWN'
                )
                if subject not in t_scores:
                    t_scores[subject] = {}
                t_scores[subject].update(subject_t_scores)

        return t_scores

    def _generate_ranks(self, scores: list, exam_info: dict) -> dict:
        """生成排名
        当select_type不是'未分科'时，按文理分类分别计算排名
        """
        ranks = {}
        subjects = ['chinese', 'math', 'english', 'physics', 'chemistry',
                    'biology', 'politics', 'history', 'geography', 'total_score']

        # 按不同维度生成排名
        dimensions = [
            ('city', None),  # 市排名（总体排名）
            ('district', 'district_name'),  # 区县排名
            ('school', 'school_name'),  # 学校排名
        ]

        # 按文理分组
        science_scores = [s for s in scores if s['select_type'] == '理科']
        liberal_scores = [s for s in scores if s['select_type'] == '文科']
        undecided_scores = [s for s in scores if s['select_type'] == '未分科']

        # 如果有已分科的学生，只按科类分别计算
        if science_scores or liberal_scores:
            # 理科学生排名
            if science_scores:
                for dim_name, group_by in dimensions:
                    # 总分排名
                    total_ranks = self.rank_calculator.calculate_total_rank(
                        scores=science_scores,
                        group_by=group_by,
                        student_type='SCIENCE'
                    )
                    key = f"total_score_{dim_name}" if dim_name != 'city' else "total_score"
                    if key not in ranks:
                        ranks[key] = {}
                    ranks[key].update(total_ranks)

                    # 单科排名
                    for subject in subjects:
                        if subject != 'total_score' and subject != 'history':  # 理科不计算历史
                            subject_ranks = self.rank_calculator.calculate_subject_rank(
                                scores=science_scores,
                                subject=subject,
                                group_by=group_by,
                                student_type='SCIENCE'
                            )
                            key = f"{subject}_{dim_name}" if dim_name != 'city' else subject
                            if key not in ranks:
                                ranks[key] = {}
                            ranks[key].update(subject_ranks)

            # 文科学生排名
            if liberal_scores:
                for dim_name, group_by in dimensions:
                    # 总分排名
                    total_ranks = self.rank_calculator.calculate_total_rank(
                        scores=liberal_scores,
                        group_by=group_by,
                        student_type='LIBERAL'
                    )
                    key = f"total_score_{dim_name}" if dim_name != 'city' else "total_score"
                    if key not in ranks:
                        ranks[key] = {}
                    ranks[key].update(total_ranks)

                    # 单科排名
                    for subject in subjects:
                        if subject != 'total_score' and subject != 'physics':  # 文科不计算物理
                            subject_ranks = self.rank_calculator.calculate_subject_rank(
                                scores=liberal_scores,
                                subject=subject,
                                group_by=group_by,
                                student_type='LIBERAL'
                            )
                            key = f"{subject}_{dim_name}" if dim_name != 'city' else subject
                            if key not in ranks:
                                ranks[key] = {}
                            ranks[key].update(subject_ranks)

        # 未分科的学生单独计算
        if undecided_scores:
            for dim_name, group_by in dimensions:
                # 总分排名
                total_ranks = self.rank_calculator.calculate_total_rank(
                    scores=undecided_scores,
                    group_by=group_by,
                    student_type='UNKNOWN'
                )
                key = f"total_score_{dim_name}" if dim_name != 'city' else "total_score"
                if key not in ranks:
                    ranks[key] = {}
                ranks[key].update(total_ranks)

                # 单科排名
                for subject in subjects:
                    if subject != 'total_score':
                        subject_ranks = self.rank_calculator.calculate_subject_rank(
                            scores=undecided_scores,
                            subject=subject,
                            group_by=group_by,
                            student_type='UNKNOWN'
                        )
                        key = f"{subject}_{dim_name}" if dim_name != 'city' else subject
                        if key not in ranks:
                            ranks[key] = {}
                        ranks[key].update(subject_ranks)

        return ranks

    def _save_tracking_data(self, exam_id: str, scores: list, t_scores: dict, ranks: dict):
        """保存跟踪数据到tracking_records表"""
        with connection.cursor() as cursor:
            # 先删除已有的记录
            cursor.execute("""
                DELETE FROM tracking_records 
                WHERE exam_id = %s
            """, [exam_id])

            # 为每个学生准备数据
            for score in scores:
                student_id = score['student_id']
                select_type = score['select_type']
                # 获取该学生的所有科目T分
                student_t_scores = {
                    subject: subject_scores.get(student_id, 0)
                    for subject, subject_scores in t_scores.items()
                }

                # 获取该学生的所有排名
                student_ranks = {
                    rank_type: type_ranks.get(student_id, 0)
                    for rank_type, type_ranks in ranks.items()
                }

                # 准备科目分数、T分和排名的JSON数据
                subject_scores = {
                    'chinese': float(score.get('chinese', 0)),
                    'math': float(score.get('math', 0)),
                    'english': float(score.get('english', 0)),
                    'physics': float(score.get('physics', 0)),
                    'chemistry': float(score.get('chemistry', 0)),
                    'biology': float(score.get('biology', 0)),
                    'politics': float(score.get('politics', 0)),
                    'history': float(score.get('history', 0)),
                    'geography': float(score.get('geography', 0))
                }

                subject_t_scores = {
                    'chinese': student_t_scores.get('chinese', 0),
                    'math': student_t_scores.get('math', 0),
                    'english': student_t_scores.get('english', 0),
                    'physics': student_t_scores.get('physics', 0),
                    'chemistry': student_t_scores.get('chemistry', 0),
                    'biology': student_t_scores.get('biology', 0),
                    'politics': student_t_scores.get('politics', 0),
                    'history': student_t_scores.get('history', 0),
                    'geography': student_t_scores.get('geography', 0)
                }

                subject_ranks = {
                    'chinese': student_ranks.get('chinese', 0),
                    'math': student_ranks.get('math', 0),
                    'english': student_ranks.get('english', 0),
                    'physics': student_ranks.get('physics', 0),
                    'chemistry': student_ranks.get('chemistry', 0),
                    'biology': student_ranks.get('biology', 0),
                    'politics': student_ranks.get('politics', 0),
                    'history': student_ranks.get('history', 0),
                    'geography': student_ranks.get('geography', 0)
                }

                # 计算加权T分（可以根据实际需求调整权重）
                weights = {
                    'chinese': 0.2,
                    'math': 0.2,
                    'english': 0.2,
                    'physics': 0.1,
                    'chemistry': 0.1,
                    'biology': 0.05,
                    'politics': 0.05,
                    'history': 0.05,
                    'geography': 0.05
                }
                weighted_t_score = sum(
                    subject_t_scores[subject] * weight
                    for subject, weight in weights.items()
                )

                # 插入记录
                cursor.execute("""
                    INSERT INTO tracking_records (
                        student_id,
                        exam_id,
                        total_score,
                        total_t_score,
                        city_rank,
                        district_rank,
                        school_rank,
                        city_t_score,
                        district_t_score,
                        school_t_score,
                        subject_scores,
                        subject_t_scores,
                        subject_ranks,
                        weighted_t_score,
                        select_type
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s
                    )
                """, [
                    student_id,
                    exam_id,
                    float(score['total_score']),
                    student_t_scores.get('total_score', 0),
                    student_ranks.get('total_score', 0),
                    student_ranks.get('total_score_district', 0),
                    student_ranks.get('total_score_school', 0),
                    student_t_scores.get('total_score', 0),  # 市T分
                    student_t_scores.get('total_score_district', 0),  # 区T分
                    student_t_scores.get('total_score_school', 0),  # 校T分
                    json.dumps(subject_scores),
                    json.dumps(subject_t_scores),
                    json.dumps(subject_ranks),
                    weighted_t_score,
                    select_type
                ])