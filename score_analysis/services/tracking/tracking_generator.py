import json
import logging
from typing import List, Dict
from django.db import transaction, connection
from .statistics_calculator import StatisticsCalculator
from .ranking_calculator import RankingCalculator


class TrackingGenerator:
    def __init__(self):
        self.stats_calculator = StatisticsCalculator()
        self.rank_calculator = RankingCalculator(self.stats_calculator)
        self.logger = logging.getLogger(__name__)  # 添加这行

    def _get_school_level(self, semester: str) -> str:
        """从学期信息获取学段
        Args:
            semester: 学期信息，例如：'高一上'、'初三下'、'小六上'
        Returns:
            str: 学段代码 'H'/'M'/'P'
        """
        try:
            if not semester:
                return 'H'

            if semester.startswith('高'):
                return 'H'
            elif semester.startswith('初'):
                return 'M'
            elif semester.startswith('小'):
                return 'P'

            return 'H'  # 默认返回高中

        except Exception as e:
            self.logger.error(f"解析学段信息时出错: {str(e)}, semester: {semester}")
            return 'H'

    def _is_stream_divided(self, exam_info: dict) -> bool:
        """判断是否分科"""
        school_level = exam_info['school_level']
        if school_level in ['P', 'M']:  # 小学、初中不分科
            return False
        if school_level == 'H' and exam_info['semester'] == '高一上':  # 高一上不分科
            return False
        return True

    def _get_subjects_config(self, school_level: str) -> List[str]:
        """获取不同学段的科目配置"""
        if school_level == 'P':  # 小学
            return ['chinese', 'math', 'english', 'physics']
        elif school_level == 'M':  # 初中
            return ['chinese', 'math', 'english', 'physics', 'chemistry',
                    'politics', 'history', 'geography', 'biology']
        else:  # 高中
            return ['chinese', 'math', 'english', 'physics', 'chemistry',
                    'biology', 'politics', 'history', 'geography']

    def generate(self, exam_id: str, generate_t_score: bool = True, generate_rank: bool = True):
        """生成发展跟踪数据"""
        try:
            # 检查是否存在已生成的数据
            if self._check_existing_data(exam_id):
                # 如果存在数据，返回特殊状态码
                return "EXISTS"

            with transaction.atomic():
                # 1. 获取考试数据
                self.logger.info(f"开始处理考试 {exam_id} 的数据")
                scores = self._get_exam_scores(exam_id)
                if not scores:
                    self.logger.warning(f"未找到考试 {exam_id} 的成绩数据")
                    return

                # 2. 获取考试基本信息
                exam_info = self._get_exam_info(exam_id)
                self.logger.info(f"考试基本信息: {exam_info}")

                # 3. 生成T分
                t_scores = {}
                if generate_t_score:
                    self.logger.info("开始生成T分")
                    t_scores = self._generate_t_scores(scores, exam_info)
                    self.logger.info(f"生成T分完成，共 {len(t_scores)} 条数据")

                # 4. 生成排名
                ranks = {}
                if generate_rank:
                    self.logger.info("开始生成排名")
                    ranks = self._generate_ranks(scores, exam_info)
                    self.logger.info(f"生成排名完成，共 {len(ranks)} 条数据")

                # 5. 保存数据
                self.logger.info("开始保存数据")
                self._save_tracking_data(exam_id, scores, t_scores, ranks)
                self.logger.info("数据保存完成")
            return "SUCCESS"
        except Exception as e:
            self.logger.error(f"生成发展跟踪数据失败: {str(e)}", exc_info=True)
            raise Exception(f"生成发展跟踪数据失败: {str(e)}")

    def _get_exam_scores(self, exam_id: str) -> list:
        """获取考试成绩数据"""
        try:
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
                        class_name
                    FROM score_student_basic
                    WHERE exam_id = %s
                """, [exam_id])
                columns = [col[0] for col in cursor.description]
                scores = [dict(zip(columns, row)) for row in cursor.fetchall()]

                if not scores:
                    self.logger.warning(f"未找到考试 {exam_id} 的成绩数据")
                    return []

                self.logger.info(f"获取到 {len(scores)} 条成绩数据")
                return scores
        except Exception as e:
            self.logger.error(f"获取考试成绩数据时出错: {str(e)}")
            raise

    def _get_exam_info(self, exam_id: str) -> dict:
        """获取考试信息
        Args:
            exam_id: 考试ID，例如：'202501-CITY-M-2025'
        Returns:
            dict: 包含考试信息的字典
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        exam_id,
                        exam_name,
                        exam_date,
                        exam_type,
                        grade_level,
                        semester,
                        status
                    FROM base_exam_config
                    WHERE exam_id = %s
                """, [exam_id])
                row = cursor.fetchone()
                if not row:
                    self.logger.error(f"未找到考试 {exam_id} 的配置信息")
                    raise ValueError(f"未找到考试 {exam_id} 的配置信息")

                exam_info = {
                    'exam_id': row[0],
                    'exam_name': row[1],
                    'exam_date': row[2],
                    'exam_type': row[3],
                    'grade_level': row[4],
                    'semester': row[5],
                    'status': row[6],
                    'school_level': self._get_school_level(row[5]),  # 使用 semester 判断学段
                    'exam_level': exam_id.split('-')[1] if len(exam_id.split('-')) >= 2 else 'CITY'
                }

                self.logger.info(f"获取到考试信息: {exam_info}")
                return exam_info

        except Exception as e:
            self.logger.error(f"获取考试信息时出错: {str(e)}")

    def _generate_t_scores(self, scores: list, exam_info: dict) -> dict:
        """生成T分
        根据学段和分科情况分别计算T分
        """
        t_scores = {}
        school_level = exam_info['school_level']
        subjects = self._get_subjects_config(school_level) + ['total_score']

        # 如果是小学、初中或高一上，直接整体计算
        if not self._is_stream_divided(exam_info):
            for subject in subjects:
                subject_t_scores = self.stats_calculator.calculate_subject_t_scores(
                    scores=scores,
                    subject=subject,
                    school_level=school_level,
                    student_type='ALL'
                )
                t_scores[subject] = subject_t_scores
            return t_scores

        # 高中已分科情况：按文理分别计算
        # 按文理分组
        science_scores = [s for s in scores if s['select_type'] == '理科']
        liberal_scores = [s for s in scores if s['select_type'] == '文科']
        undecided_scores = [s for s in scores if s['select_type'] == '未确定']

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
                        school_level=school_level,
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
                        school_level=school_level,
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
                    school_level=school_level,
                    student_type='UNKNOWN'
                )
                if subject not in t_scores:
                    t_scores[subject] = {}
                t_scores[subject].update(subject_t_scores)

        return t_scores

    def _generate_ranks(self, scores: list, exam_info: dict) -> dict:
        """生成排名
        根据学段和分科情况分别计算排名
        """
        ranks = {}
        school_level = exam_info['school_level']
        subjects = self._get_subjects_config(school_level) + ['total_score']

        dimensions = [
            ('city', None),  # 市排名（总体排名）
            ('district', 'district_name'),  # 区县排名
            ('school', 'school_name'),  # 学校排名
        ]

        # 如果是小学、初中或高一上，直接整体排名
        if not self._is_stream_divided(exam_info):
            for dim_name, group_by in dimensions:
                # 总分排名
                total_ranks = self.rank_calculator.calculate_total_rank(
                    scores=scores,
                    group_by=group_by,
                    student_type='ALL',
                    exam_info=exam_info  # 添加考试信息
                )
                key = f"total_score_{dim_name}" if dim_name != 'city' else "total_score"
                ranks[key] = total_ranks

                # 单科排名
                for subject in subjects:
                    if subject != 'total_score':
                        subject_ranks = self.rank_calculator.calculate_subject_rank(
                            scores=scores,
                            subject=subject,
                            group_by=group_by,
                            student_type='ALL',
                            exam_info=exam_info  # 添加考试信息
                        )
                        key = f"{subject}_{dim_name}" if dim_name != 'city' else subject
                        ranks[key] = subject_ranks
            return ranks

        # 高中已分科情况：按文理分别计算
        science_scores = [s for s in scores if s['select_type'] == '理科']
        liberal_scores = [s for s in scores if s['select_type'] == '文科']
        undecided_scores = [s for s in scores if s['select_type'] == '未确定']

        # 如果有已分科的学生，只按科类分别计算
        if science_scores or liberal_scores:
            # 理科学生排名
            if science_scores:
                for dim_name, group_by in dimensions:
                    # 总分排名
                    total_ranks = self.rank_calculator.calculate_total_rank(
                        scores=science_scores,
                        group_by=group_by,
                        student_type='SCIENCE',
                        exam_info=exam_info  # 添加考试信息
                    )
                    key = f"total_score_{dim_name}" if dim_name != 'city' else "total_score"
                    if key not in ranks:
                        ranks[key] = {}
                    ranks[key].update(total_ranks)

                    # 单科排名
                    for subject in subjects:
                        if subject != 'total_score' and subject != 'history':
                            subject_ranks = self.rank_calculator.calculate_subject_rank(
                                scores=science_scores,
                                subject=subject,
                                group_by=group_by,
                                student_type='SCIENCE',
                                exam_info=exam_info  # 添加考试信息
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
                        student_type='LIBERAL',
                        exam_info=exam_info  # 添加考试信息
                    )
                    key = f"total_score_{dim_name}" if dim_name != 'city' else "total_score"
                    if key not in ranks:
                        ranks[key] = {}
                    ranks[key].update(total_ranks)

                    # 单科排名
                    for subject in subjects:
                        if subject != 'total_score' and subject != 'physics':
                            subject_ranks = self.rank_calculator.calculate_subject_rank(
                                scores=liberal_scores,
                                subject=subject,
                                group_by=group_by,
                                student_type='LIBERAL',
                                exam_info=exam_info  # 添加考试信息
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
                    student_type='UNKNOWN',
                    exam_info=exam_info  # 添加考试信息
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
                            student_type='UNKNOWN',
                            exam_info=exam_info  # 添加考试信息
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

    def _get_weights_config(self, school_level: str, select_type: str = '未确定') -> Dict[str, float]:
        """获取不同学段的科目权重配置"""
        if school_level == 'P':
            return {
                'chinese': 0.3,
                'math': 0.3,
                'english': 0.2,
                'physics': 0.2
            }
        elif school_level == 'M':
            return {
                'chinese': 0.2,
                'math': 0.2,
                'english': 0.2,
                'physics': 0.1,
                'chemistry': 0.1,
                'politics': 0.05,
                'history': 0.05,
                'geography': 0.05,
                'biology': 0.05
            }
        elif school_level == 'H':
            if select_type == '理科':
                return {
                    'chinese': 0.15,
                    'math': 0.15,
                    'english': 0.15,
                    'physics': 0.15,
                    'chemistry': 0.15,
                    'biology': 0.15,
                    'politics': 0.05,
                    'history': 0.025,
                    'geography': 0.025
                }
            elif select_type == '文科':
                return {
                    'chinese': 0.15,
                    'math': 0.15,
                    'english': 0.15,
                    'history': 0.15,
                    'politics': 0.15,
                    'geography': 0.15,
                    'physics': 0.05,
                    'chemistry': 0.025,
                    'biology': 0.025
                }
            else:  # 未确定
                return {
                    'chinese': 0.2,
                    'math': 0.2,
                    'english': 0.2,
                    'physics': 0.1,
                    'chemistry': 0.1,
                    'politics': 0.05,
                    'history': 0.05,
                    'geography': 0.05,
                    'biology': 0.05
                }

    def _check_existing_data(self, exam_id: str) -> bool:
        """检查是否存在已生成的数据"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(1)
                    FROM tracking_records
                    WHERE exam_id = %s
                    LIMIT 1
                """, [exam_id])
                count = cursor.fetchone()[0]
                return count > 0
        except Exception as e:
            self.logger.error(f"检查已存在数据时出错: {str(e)}")
            return False

    def _clear_existing_data(self, exam_id: str) -> bool:
        """清空已存在的数据"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM tracking_records
                    WHERE exam_id = %s
                """, [exam_id])
                return True
        except Exception as e:
            self.logger.error(f"清空已存在数据时出错: {str(e)}")
            return False


    def _is_stream_divided(self, exam_info: dict) -> bool:
        """判断是否需要分科处理
        Args:
            exam_info: 考试信息字典
        Returns:
            bool: True 表示需要分科处理，False 表示不需要分科
        """
        try:
            semester = exam_info.get('semester', '')

            # 只有高一下、高二、高三需要分科
            if semester.startswith(('高一下', '高二', '高三')):
                return True

            return False

        except Exception as e:
            self.logger.error(f"判断分科状态时出错: {str(e)}")
            return False