from typing import List, Dict, Tuple, Optional
import pandas as pd
import numpy as np
import time
from scipy import stats
from django.db import connection
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ScoreAnalysisForValueAddService:
    """
    增值评估成绩分析服务类，用于计算T分数和进行教学质量增值评估。

    该服务提供以下功能：
    1. 按文理科分别计算T分数（使用全市数据作为标准）
    2. 考虑不同科目的满分值（语数外150分，其他科目100分）
    3. 排除未选科目（分数为-3）
    4. 分析学校教学质量增值情况
    5. 评估学生进步情况

    主要分析维度：
    1. 学科维度：各科目T分变化
    2. 学校维度：整体教学质量增值
    3. 学生维度：个体进步情况

    Attributes:
        SUBJECT_CONFIG (Dict): 文理科科目配置，包含科目列表和满分值
        SUBJECT_NAMES (Dict): 科目代码与中文名称映射
    """

    SUBJECT_CONFIG = {
        '理科': {
            'subjects': ['chinese', 'math', 'english', 'physics', 'chemistry', 'biology', 'geography'],
            'max_scores': {
                'chinese': 150, 'math': 150, 'english': 150,
                'physics': 100, 'chemistry': 100, 'biology': 100, 'geography': 100
            }
        },
        '文科': {
            'subjects': ['chinese', 'math', 'english', 'history', 'politics', 'geography', 'biology'],
            'max_scores': {
                'chinese': 150, 'math': 150, 'english': 150,
                'history': 100, 'politics': 100, 'geography': 100, 'biology': 100
            }
        }
    }

    SUBJECT_NAMES = {
        'chinese': '语文',
        'math': '数学',
        'english': '英语',
        'physics': '物理',
        'chemistry': '化学',
        'biology': '生物',
        'history': '历史',
        'politics': '政治',
        'geography': '地理'
    }

    def __init__(self, exam_ids: List[str], district_name: str = '开平市'):
        """
        初始化成绩分析服务。

        Args:
            exam_ids: 考试ID列表，按时间顺序排列
            district_name: 区域名称，默认为'开平市'

        Raises:
            ValueError: 如果exam_ids为空或district_name无效
        """
        if not exam_ids:
            raise ValueError("考试ID列表不能为空")

        self.exam_ids = sorted(exam_ids)
        self.district_name = district_name
        self.scores_df: Optional[pd.DataFrame] = None
        self.t_scores_df: Optional[pd.DataFrame] = None
        self.base_exam_id: str = self.exam_ids[0]
        self.city_stats: Dict[Tuple[str, str, str], Dict] = {}

        logger.info(f"初始化成绩分析服务 - 考试IDs: {exam_ids}, 区域: {district_name}")

    def prepare_data(self) -> None:
        """
        准备分析数据，从数据库获取成绩并进行预处理。
        """
        try:
            logger.info(f"开始准备数据分析，考试ID列表: {self.exam_ids}")

            sql = """
            SELECT 
                exam_id, student_id, student_name, district_name,
                school_name, class_name, select_type,
                chinese, math, english, physics, chemistry,
                biology, history, politics, geography, total_score
            FROM score_student_basic
            WHERE exam_id IN %s
            """

            start_time = time.time()
            with connection.cursor() as cursor:
                # 直接执行查询，不进行编码转换
                cursor.execute(sql, [tuple(self.exam_ids)])
                columns = [col[0] for col in cursor.description]

                # 直接获取原始数据
                scores = [dict(zip(columns, row)) for row in cursor.fetchall()]

            query_time = time.time() - start_time
            logger.info(f"数据库查询耗时: {query_time:.2f}秒")

            # 创建DataFrame
            self.scores_df = pd.DataFrame(scores)

            if self.scores_df.empty:
                raise ValueError("未找到考试数据")

            logger.info(f"成功获取原始成绩数据，共 {len(self.scores_df)} 条记录")

            # 数据类型转换
            start_time = time.time()

            # 转换数值列
            score_columns = ['chinese', 'math', 'english', 'physics', 'chemistry',
                             'biology', 'history', 'politics', 'geography', 'total_score']

            for col in score_columns:
                if col in self.scores_df.columns:
                    logger.debug(f"转换 {col} 列数据类型")
                    self.scores_df[col] = pd.to_numeric(
                        self.scores_df[col],
                        errors='coerce'
                    ).fillna(-3)

            # 确保字符串列的类型正确
            string_columns = ['student_name', 'district_name', 'school_name',
                              'class_name', 'select_type', 'exam_id', 'student_id']

            for col in string_columns:
                if col in self.scores_df.columns:
                    self.scores_df[col] = self.scores_df[col].astype(str)

            conversion_time = time.time() - start_time
            logger.info(f"数据类型转换耗时: {conversion_time:.2f}秒")

            # 计算T分
            start_time = time.time()
            logger.info("开始计算T分...")
            self.t_scores_df = self._calculate_t_scores()
            t_score_time = time.time() - start_time
            logger.info(f"T分计算耗时: {t_score_time:.2f}秒")

            total_time = query_time + conversion_time + t_score_time
            logger.info(f"数据准备总耗时: {total_time:.2f}秒")

        except Exception as e:
            logger.error(f"数据准备错误: {str(e)}")
            raise Exception(f"数据准备错误: {str(e)}")

    def _calculate_t_scores(self) -> pd.DataFrame:
        """
        计算T分数。

        使用全市数据计算均值和标准差，但只输出指定区域学生的T分。
        T分计算公式：T = 10Z + 50，其中Z为标准分。
        排除未选科目（分数为-3）的情况。

        Returns:
            pd.DataFrame: 包含T分数据的DataFrame

        Raises:
            ValueError: 如果无法生成有效的T分数据
        """
        t_scores_list = []

        for exam_id in self.exam_ids:
            for select_type in ['文科', '理科']:
                exam_type_data = self._get_exam_type_data(exam_id, select_type)
                if exam_type_data.empty:
                    continue

                subject_config = self.SUBJECT_CONFIG[select_type]
                subjects = subject_config['subjects']
                max_scores = subject_config['max_scores']

                for subject in subjects:
                    try:
                        # 获取有效成绩（排除-3和0分，且不超过满分）
                        valid_scores = exam_type_data[
                            (exam_type_data[subject] > 0) &
                            (exam_type_data[subject] != -3) &
                            (exam_type_data[subject] <= max_scores[subject])
                            ]

                        if valid_scores.empty:
                            logger.warning(f"警告: {exam_id} {select_type} {subject} 没有有效成绩")
                            continue

                        # 计算全市统计数据
                        city_mean = valid_scores[subject].mean()
                        city_std = valid_scores[subject].std()

                        # 存储统计数据
                        stats_key = (exam_id, select_type, subject)
                        self.city_stats[stats_key] = {
                            'mean': city_mean,
                            'std': city_std,
                            'count': len(valid_scores),
                            'max_score': valid_scores[subject].max(),
                            'min_score': valid_scores[subject].min(),
                            'full_score': max_scores[subject],
                            'avg_rate': (city_mean / max_scores[subject]) * 100,
                            'valid_count': len(valid_scores),
                            'total_count': len(exam_type_data),
                            'selection_rate': (len(valid_scores) / len(exam_type_data)) * 100
                        }

                        # 处理指定区域的学生
                        district_scores = valid_scores[valid_scores['district_name'] == self.district_name]

                        if not district_scores.empty and city_std != 0:
                            z_scores = (district_scores[subject] - city_mean) / city_std
                            t_scores = z_scores * 10 + 50

                            for index, row in district_scores.iterrows():
                                t_scores_list.append({
                                    'exam_id': exam_id,
                                    'student_id': row['student_id'],
                                    'student_name': row['student_name'],
                                    'school_name': row['school_name'],
                                    'class_name': row['class_name'],
                                    'select_type': select_type,
                                    'subject': subject,
                                    'subject_name': self.SUBJECT_NAMES[subject],
                                    'raw_score': row[subject],
                                    't_score': t_scores[index],
                                    'city_mean': city_mean,
                                    'city_std': city_std,
                                    'max_score': max_scores[subject],
                                    'score_rate': (row[subject] / max_scores[subject]) * 100,
                                    'percentile': stats.percentileofscore(
                                        valid_scores[subject],
                                        row[subject]
                                    )
                                })

                    except Exception as e:
                        logger.error(f"计算T分时出错 (考试: {exam_id}, 类型: {select_type}, 学科: {subject}): {str(e)}")
                        continue

        t_scores_df = pd.DataFrame(t_scores_list)

        if t_scores_df.empty:
            raise ValueError("未能生成有效的T分数据")

        logger.info(f"T分计算完成，共生成 {len(t_scores_df)} 条记录")
        self._log_statistics_summary(t_scores_df)

        return t_scores_df

    def _get_exam_type_data(self, exam_id: str, select_type: str) -> pd.DataFrame:
        """
        获取指定考试和科类的数据。

        Args:
            exam_id: 考试ID
            select_type: 科类（'文科'或'理科'）

        Returns:
            pd.DataFrame: 符合条件的成绩数据
        """
        return self.scores_df[
            (self.scores_df['exam_id'] == exam_id) &
            (self.scores_df['select_type'] == select_type)
            ]

    def _log_statistics_summary(self, df: pd.DataFrame) -> None:
        """
        记录统计信息汇总。

        Args:
            df: T分数据DataFrame
        """
        logger.info("\n=== T分计算统计汇总 ===")
        logger.info(f"总记录数: {len(df)}")

        for select_type in ['文科', '理科']:
            type_df = df[df['select_type'] == select_type]
            logger.info(f"\n{select_type}统计:")
            logger.info(f"记录数: {len(type_df)}")

            subject_config = self.SUBJECT_CONFIG[select_type]
            for subject in subject_config['subjects']:
                subject_df = type_df[type_df['subject'] == subject]
                if not subject_df.empty:
                    logger.info(f"\n{self.SUBJECT_NAMES[subject]}:")
                    logger.info(f"  记录数: {len(subject_df)}")
                    logger.info(f"  选考率: {self._get_selection_rate(subject_df):.2f}%")
                    logger.info(f"  T分均值: {subject_df['t_score'].mean():.2f}")
                    logger.info(f"  T分标准差: {subject_df['t_score'].std():.2f}")
                    logger.info(f"  原始分均值: {subject_df['raw_score'].mean():.2f}")
                    logger.info(f"  得分率: {subject_df['score_rate'].mean():.2f}%")

    def _get_selection_rate(self, subject_df: pd.DataFrame) -> float:
        """
        计算选考率。

        Args:
            subject_df: 学科成绩DataFrame

        Returns:
            float: 选考率百分比
        """
        if not subject_df.empty:
            exam_id = subject_df['exam_id'].iloc[0]
            select_type = subject_df['select_type'].iloc[0]
            subject = subject_df['subject'].iloc[0]
            stats_key = (exam_id, select_type, subject)
            if stats_key in self.city_stats:
                return self.city_stats[stats_key]['selection_rate']
        return 0.0

    def get_city_statistics_summary(self) -> Dict:
        """
        获取全市统计数据汇总。

        Returns:
            Dict: 包含全市统计数据的字典
        """
        summary = {}
        for (exam_id, select_type, subject), stats in self.city_stats.items():
            key = f"{exam_id}_{select_type}_{subject}"
            summary[key] = {
                'exam_id': exam_id,
                'select_type': select_type,
                'subject': subject,
                'subject_name': self.SUBJECT_NAMES[subject],
                'mean': round(stats['mean'], 2),
                'std': round(stats['std'], 2),
                'count': stats['count'],
                'max_score': stats['max_score'],
                'min_score': stats['min_score'],
                'full_score': stats['full_score'],
                'avg_rate': round(stats['avg_rate'], 2),
                'selection_rate': round(stats['selection_rate'], 2)
            }
        return summary

    def analyze_school_progress(self) -> Dict:
        """
        分析学校进步情况。

        Returns:
            Dict: 包含学校进步分析结果的字典

        Raises:
            ValueError: 如果T分数据未准备好
        """
        if self.t_scores_df is None:
            raise ValueError("请先调用prepare_data()准备数据")

        progress_results = {}

        # 按学校和科类分组分析
        for (school_name, select_type), school_data in self.t_scores_df.groupby(['school_name', 'select_type']):
            try:
                base_exam_data = school_data[school_data['exam_id'] == self.base_exam_id]
                if base_exam_data.empty:
                    continue

                school_key = f"{school_name}_{select_type}"
                progress_results[school_key] = self._analyze_single_school(
                    school_name,
                    select_type,
                    school_data
                )

            except Exception as e:
                logger.error(f"分析学校 {school_name} ({select_type}) 进步情况时出错: {str(e)}")
                continue

        return progress_results

    def _analyze_single_school(self, school_name: str, select_type: str, school_data: pd.DataFrame) -> Dict:
        """
        分析单个学校的进步情况。

        Args:
            school_name: 学校名称
            select_type: 科类（'文科'或'理科'）
            school_data: 学校成绩数据

        Returns:
            Dict: 包含学校进步分析结果的字典
        """
        base_exam_data = school_data[school_data['exam_id'] == self.base_exam_id]
        subjects = self.SUBJECT_CONFIG[select_type]['subjects']

        result = {
            'school_name': school_name,
            'select_type': select_type,
            'base_exam_id': self.base_exam_id,
            'subject_progress': {},
            'overall_progress': {},
            'student_progress': {}
        }

        # 分析各科目进步情况
        for subject in subjects:
            subject_progress = self._analyze_subject_progress(
                school_data,
                base_exam_data,
                subject
            )
            if subject_progress:
                result['subject_progress'][subject] = subject_progress

        # 计算整体进步情况
        result['overall_progress'] = self._calculate_overall_progress(school_data)

        # 分析学生个体进步情况
        result['student_progress'] = self._analyze_student_progress(school_data)

        return result

    def _analyze_subject_progress(self, school_data: pd.DataFrame,
                                  base_exam_data: pd.DataFrame,
                                  subject: str) -> Dict:
        """
        分析单个学科的进步情况。

        Args:
            school_data: 学校所有成绩数据
            base_exam_data: 基准考试数据
            subject: 学科名称

        Returns:
            Dict: 包含学科进步分析结果的字典
        """
        subject_base = base_exam_data[base_exam_data['subject'] == subject]
        if subject_base.empty:
            return {}

        base_mean_t = subject_base['t_score'].mean()
        base_mean_raw = subject_base['raw_score'].mean()

        progress_data = []

        for exam_id in self.exam_ids[1:]:  # 跳过基准考试
            exam_data = school_data[
                (school_data['exam_id'] == exam_id) &
                (school_data['subject'] == subject)
                ]

            if not exam_data.empty:
                current_mean_t = exam_data['t_score'].mean()
                current_mean_raw = exam_data['raw_score'].mean()

                progress_data.append({
                    'exam_id': exam_id,
                    't_score_change': current_mean_t - base_mean_t,
                    'raw_score_change': current_mean_raw - base_mean_raw,
                    'current_mean_t': current_mean_t,
                    'current_mean_raw': current_mean_raw,
                    'student_count': len(exam_data)
                })

        return {
            'subject_name': self.SUBJECT_NAMES[subject],
            'base_mean_t': base_mean_t,
            'base_mean_raw': base_mean_raw,
            'progress_data': progress_data
        }

    def _calculate_overall_progress(self, school_data: pd.DataFrame) -> Dict:
        """
        计算学校整体进步情况。

        Args:
            school_data: 学校成绩数据

        Returns:
            Dict: 包含整体进步分析结果的字典
        """
        base_data = school_data[school_data['exam_id'] == self.base_exam_id]
        base_mean_t = base_data['t_score'].mean()

        progress_data = []

        for exam_id in self.exam_ids[1:]:
            exam_data = school_data[school_data['exam_id'] == exam_id]
            if not exam_data.empty:
                current_mean_t = exam_data['t_score'].mean()
                progress_data.append({
                    'exam_id': exam_id,
                    't_score_change': current_mean_t - base_mean_t,
                    'current_mean_t': current_mean_t,
                    'student_count': len(exam_data)
                })

        return {
            'base_mean_t': base_mean_t,
            'progress_data': progress_data
        }

    def _analyze_student_progress(self, school_data: pd.DataFrame) -> Dict:
        """
        分析学生个体进步情况。

        Args:
            school_data: 学校成绩数据

        Returns:
            Dict: 包含学生进步分析结果的字典
        """
        base_students = set(school_data[school_data['exam_id'] == self.base_exam_id]['student_id'])

        progress_stats = []

        for exam_id in self.exam_ids[1:]:
            current_data = school_data[school_data['exam_id'] == exam_id]
            current_students = set(current_data['student_id'])

            # 获取共同的学生
            common_students = base_students & current_students

            if common_students:
                progress_count = 0
                significant_progress_count = 0

                for student_id in common_students:
                    base_scores = school_data[
                        (school_data['exam_id'] == self.base_exam_id) &
                        (school_data['student_id'] == student_id)
                        ]
                    current_scores = current_data[current_data['student_id'] == student_id]

                    if not base_scores.empty and not current_scores.empty:
                        base_mean_t = base_scores['t_score'].mean()
                        current_mean_t = current_scores['t_score'].mean()

                        if current_mean_t > base_mean_t:
                            progress_count += 1
                            if current_mean_t - base_mean_t > 10:
                                significant_progress_count += 1

                total_students = len(common_students)
                progress_stats.append({
                    'exam_id': exam_id,
                    'common_student_count': total_students,
                    'progress_count': progress_count,
                    'progress_rate': (progress_count / total_students) * 100 if total_students > 0 else 0,
                    'significant_progress_count': significant_progress_count,
                    'significant_progress_rate': (
                                            significant_progress_count / total_students) * 100 if total_students > 0 else 0
                })

        return {'progress_stats': progress_stats}

    def get_analysis_results(self) -> Dict:
        """
        获取完整的分析结果。

        Returns:
            Dict: 包含以下键的字典：
                - city_stats: 全市统计数据
                - t_scores: T分数据
                - progress_analysis: 进步分析结果

        Raises:
            ValueError: 如果T分数据未准备好
        """
        if self.t_scores_df is None:
            raise ValueError("请先调用prepare_data()准备数据")

        return {
            'city_stats': self.get_city_statistics_summary(),
            't_scores': self.t_scores_df.to_dict('records'),
            'progress_analysis': self.analyze_school_progress()
        }