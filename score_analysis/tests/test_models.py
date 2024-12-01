# score_analysis/tests/test_models.py

from django.test import TestCase
from score_analysis.models import (
    ScoreStudentBasic,
    SubjectTScore,
    SubjectStatistics,
    BaseExamConfig,
    ScoreRankings,
    ScoreDistributions
)
from decimal import Decimal


class TestScoreStudentBasic(TestCase):


    def setUp(self):
        """设置测试数据"""
        # 先创建考试配置
        self.exam_config = BaseExamConfig.objects.create(
            exam_id='TEST001',
            exam_name='测试考试',
            exam_date='2024-01-01'
        )
        # 创建一个理科学生数据
        self.science_student = ScoreStudentBasic.objects.create(
            exam_id='TEST001',
            student_id='25100010001',
            student_name='理科生',
            district_name='测试区',
            school_name='测试中学',
            class_field='1班',
            select_type='理科',
            chinese=Decimal('120.5'),
            math=Decimal('140.0'),
            english=Decimal('130.0'),
            physics=Decimal('90.0'),
            chemistry=Decimal('85.0'),
            biology=Decimal('88.0'),
            history=Decimal('0.0'),
            politics=Decimal('0.0'),
            geography=Decimal('0.0')
        )

        # 创建一个文科学生数据
        self.liberal_student = ScoreStudentBasic.objects.create(
            exam_id='TEST001',
            student_id='25100010002',
            student_name='文科生',
            district_name='测试区',
            school_name='测试中学',
            class_field='2班',
            select_type='文科',
            chinese=Decimal('125.5'),
            math=Decimal('135.0'),
            english=Decimal('138.0'),
            physics=Decimal('0.0'),
            chemistry=Decimal('0.0'),
            biology=Decimal('0.0'),
            history=Decimal('92.0'),
            politics=Decimal('89.0'),
            geography=Decimal('91.0')
        )

    def test_get_subject_score(self):
        """测试获取科目分数方法"""
        # 测试理科生成绩
        self.assertEqual(self.science_student.get_subject_score('chinese'), Decimal('120.5'))
        self.assertEqual(self.science_student.get_subject_score('physics'), Decimal('90.0'))
        self.assertEqual(self.science_student.get_subject_score('history'), Decimal('0.0'))

        # 测试文科生成绩
        self.assertEqual(self.liberal_student.get_subject_score('chinese'), Decimal('125.5'))
        self.assertEqual(self.liberal_student.get_subject_score('physics'), Decimal('0.0'))
        self.assertEqual(self.liberal_student.get_subject_score('history'), Decimal('92.0'))

        # 测试不存在的科目
        self.assertIsNone(self.science_student.get_subject_score('invalid_subject'))

    def test_determine_stream_type(self):
        """测试判断文理科方法"""
        # 测试理科生
        self.assertEqual(self.science_student.determine_stream_type(), '理科')

        # 测试文科生
        self.assertEqual(self.liberal_student.determine_stream_type(), '文科')

        # 创建一个未确定的学生（没有物理和历史成绩）
        undetermined_student = ScoreStudentBasic.objects.create(
            exam_id='TEST001',
            student_id='25100010003',
            student_name='未定科生',
            district_name='测试区',
            school_name='测试中学',
            class_field='3班',
            select_type='未确定',
            chinese=Decimal('120.0'),
            math=Decimal('130.0'),
            english=Decimal('125.0'),
            physics=Decimal('0.0'),
            chemistry=Decimal('0.0'),
            biology=Decimal('0.0'),
            history=Decimal('0.0'),
            politics=Decimal('0.0'),
            geography=Decimal('0.0')
        )
        self.assertEqual(undetermined_student.determine_stream_type(), '未确定')


class TestStatisticalModels(TestCase):
    """测试统计相关模型"""

    def setUp(self):
        """设置测试数据"""
        # ... 设置基础数据

    def test_t_score_creation(self):
        """测试T分创建"""
        t_score = SubjectTScore.objects.create(
            exam=self.exam_config,
            unified_student_id='25100010001',
            subject=self.subject_config,
            stream_type='理科',
            level_type='city',
            raw_score=Decimal('90.0'),
            t_score=Decimal('60.5'),
            z_score=Decimal('1.05')
        )
        self.assertIsNotNone(t_score.score_id)

    def test_statistics_creation(self):
        """测试统计值创建"""
        stats = SubjectStatistics.objects.create(
            exam=self.exam_config,
            subject=self.subject_config,
            stream_type='理科',
            level_type='city',
            sample_size=100,
            mean=Decimal('85.5'),
            std_dev=Decimal('10.2')
        )
        self.assertIsNotNone(stats.stat_id)