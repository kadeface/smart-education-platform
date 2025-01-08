from django.db import transaction
from django.db.models import Q,Max,Min,Avg,StdDev

from score_analysis.models import BaseExamConfig, ScoreStudentBasic
from score_analysis.models.statistics import ExamLevelStatistics, ExamLevelAnalysisTask, ExamLevelAnalysisConfig
import logging
logger = logging.getLogger(__name__)

class ExamLevelStatisticsGenerator:
    """考试分层统计数据（市/区/校三级统计）

    功能说明：
    1. 层级统计：
        - 市级：整体考试情况统计
        - 区县：各区县考试情况统计
        - 学校：各学校考试情况统计

    2. 分科支持：
        - 支持文理分科统计
        - 支持未分科统计

    3. 统计指标：
        a) 基础统计指标 (basic_stats):
            - 考生人数
            - 最高分/最低分
            - 平均分
            - 标准差

        b) 排名分布统计 (ranking_stats):
            - TOP10/20/50/100/200/500的学校分布
            - 记录每个排名段内各学校的人数
            - 示例：{'TOP10': {'学校A': 5, '学校B': 3...}}

        c) 分数线统计 (score_lines):
            - 包含C9/985/211/特控/本科/专科等线
            - 记录每条线的分数、达线人数和比例
            - 示例：{'985': {'line': 650, 'count': 100, 'rate': 10.5}}

    4. 数据用途：
        - 考试整体情况分析
        - 区域间横向对比
        - 学校间横向对比
        - 分数线达线分析
        - 高端生源分布分析

    使用场景：
    1. 市级分析：
        >>> city_stats = ExamLevelStatistics.objects.get(
        ...     exam_id='202411-DIST-H-2025',
        ...     level_type='city'
        ... )
        >>> city_stats.basic_stats  # 获取市级基础统计
        >>> city_stats.ranking_stats['TOP100']  # 获取市级TOP100分布

    2. 区县分析：
        >>> district_stats = ExamLevelStatistics.objects.get(
        ...     exam_id='202411-DIST-H-2025',
        ...     level_type='district',
        ...     district_name='海淀区'
        ... )
        >>> district_stats.score_lines['985']  # 获取区级985分数线

    3. 学校分析：
        >>> school_stats = ExamLevelStatistics.objects.get(
        ...     exam_id='202411-DIST-H-2025',
        ...     level_type='school',
        ...     school_name='某中学'
        ... )
        >>> school_stats.basic_stats  # 获取学校基础统计
    """
    # 默认配置
    DEFAULT_CONFIGS = {
        'city': {
            'rank_ranges': [10, 20, 50, 100, 200, 500],
            'score_lines': {
                'C9': 0.02,     # 前2%
                '985': 0.05,    # 前5%
                '211': 0.10,    # 前10%
                '特控': 0.20,    # 前20%
                '本科': 0.60,    # 前60%
                '专科': 0.90,    # 前90%
            }
        },
        'district': {
            'rank_ranges': [10, 20, 50, 100],
            'score_lines': {
                '985': 0.05,    # 前5%
                '211': 0.10,    # 前10%
                '本科': 0.60,    # 前60%
                '专科': 0.90,    # 前90%
            }
        },
        'school': {
            'rank_ranges': [10, 20, 50],
            'score_lines': {
                '本科': 0.60,    # 前60%
                '专科': 0.90,    # 前90%
            }
        }
    }

    def __init__(self, exam_id):
        """初始化统计生成器

        Args:
            exam_id: 考试ID
        """
        self.exam_id = exam_id
        self.exam_config = self._get_exam_config()

    def _get_exam_config(self):
        """获取考试配置"""
        try:
            return BaseExamConfig.objects.get(id=self.exam_id)
        except Exception as e:
            logger.error(f"获取考试配置失败: exam_id={self.exam_id}, error={str(e)}")
            return None

    def _load_level_config(self, select_type):
        """加载分层分析配置

        Args:
            select_type: 分科类型（文科/理科/未分科）
        """
        try:
            config = ExamLevelAnalysisConfig.objects.filter(
                exam_id=self.exam_id,
                select_type=select_type,
                is_active=True
            ).first()

            if not config:
                logger.warning(f"未找到考试配置: exam_id={self.exam_id}, select_type={select_type}")

            return config

        except Exception as e:
            logger.error(f"加载考试配置失败: error={str(e)}")
            return None

    def _get_rank_ranges(self, config, district_name=None):
        """获取排名范围配置"""
        if not config:
            return []

        rank_ranges = config.rank_ranges
        area = district_name or '市级'
        return rank_ranges.get(area) or rank_ranges.get('default', [])

    def _get_score_lines(self, config):
        """获取分数线配置"""
        if not config:
            return {}

        return config.score_lines
    @classmethod
    def from_task(cls, task_id):
        """从任务创建生成器

        Args:
            task_id: 任务ID

        Returns:
            ExamLevelAnalysisGenerator实例
        """
        task = ExamLevelAnalysisTask.objects.get(id=task_id)
        return cls(config=task.config)

    def _is_division_exam(self, exam_config):
        """判断是否为分科考试

        判断规则：
        1. 考试ID以'-H-'结尾（表示高中考试）
        2. 不是高一上学期的考试

        Args:
            exam_config: BaseExamConfig实例

        Returns:
            bool: 是否为分科考试
        """
        try:
            # 检查是否为高中考试
            is_high_school = exam_config.exam_id.endswith('-H-')

            # 检查是否为高一上学期
            is_first_semester = exam_config.semester == '高一上'

            # 高中考试且不是高一上学期，则为分科考试
            return is_high_school and not is_first_semester

        except Exception as e:
            logger.error(f"判断考试类型失败: exam_id={exam_config.exam_id}, error={str(e)}")
            # 默认为未分科
            return False

    def _get_districts(self, exam_id):
        """获取考试涉及的区县列表

        Args:
            exam_id: 考试ID

        Returns:
            list: 区县名称列表
        """
        try:
            return (ScoreStudentBasic.objects
                    .filter(exam_id=exam_id)
                    .values_list('district_name', flat=True)
                    .distinct()
                    .order_by('district_name'))

        except Exception as e:
            logger.error(f"获取区县列表失败: exam_id={exam_id}, error={str(e)}")
            return []

    def _get_schools(self, exam_id):
        """获取考试涉及的学校列表

        Args:
            exam_id: 考试ID

        Returns:
            list: 学校名称列表
        """
        try:
            return (ScoreStudentBasic.objects
                    .filter(exam_id=exam_id)
                    .values_list('school_name', flat=True)
                    .distinct()
                    .order_by('school_name'))

        except Exception as e:
            logger.error(f"获取学校列表失败: exam_id={exam_id}, error={str(e)}")
            return []

    def generate_analysis(self, exam_id):
        """生成考试分析

        处理流程：
        1. 获取考试配置
        2. 判断是否分科
        3. 生成三级统计数据

        Args:
            exam_id: 考试ID

        Returns:
            bool: 是否成功
        """
        try:
            exam_config = BaseExamConfig.objects.get(id=exam_id)
            is_division = self._is_division_exam(exam_config)

            with transaction.atomic():
                # 1. 生成市级统计
                self._generate_city_statistics(exam_id, is_division)

                # 2. 生成区县统计
                districts = self._get_districts(exam_id)
                for district in districts:
                    self._generate_district_statistics(
                        exam_id, district, is_division
                    )

                # 3. 生成学校统计
                schools = self._get_schools(exam_id)
                for school in schools:
                    self._generate_school_statistics(
                        exam_id, school, is_division
                    )

            logger.info(f"考试分析数据生成完成: exam_id={exam_id}")
            return True

        except Exception as e:
            logger.error(f"生成考试分析失败: exam_id={exam_id}, error={str(e)}")
            raise

    def _generate_city_statistics(self, exam_id, is_division):
        """生成市级统计"""
        if is_division:
            for select_type in ['文科', '理科']:
                self._generate_level_statistics(
                    exam_id=exam_id,
                    select_type=select_type,
                    level_type='city'
                )
        else:
            self._generate_level_statistics(
                exam_id=exam_id,
                select_type='未分科',
                level_type='city'
            )

    def _generate_district_statistics(self, exam_id, district, is_division):
        """生成区县统计"""
        if is_division:
            for select_type in ['文科', '理科']:
                self._generate_level_statistics(
                    exam_id=exam_id,
                    select_type=select_type,
                    level_type='district',
                    district_name=district
                )
        else:
            self._generate_level_statistics(
                exam_id=exam_id,
                select_type='未分科',
                level_type='district',
                district_name=district
            )

    def _generate_school_statistics(self, exam_id, school, is_division):
        """生成学校统计"""
        if is_division:
            for select_type in ['文科', '理科']:
                self._generate_level_statistics(
                    exam_id=exam_id,
                    select_type=select_type,
                    level_type='school',
                    school_name=school
                )
        else:
            self._generate_level_statistics(
                exam_id=exam_id,
                select_type='未分科',
                level_type='school',
                school_name=school
            )

    def _generate_level_statistics(self, exam_id, select_type, level_type,
                                 district_name=None, school_name=None):
        """生成指定层级的统计数据"""
        try:
            # 加载配置
            config = self._load_level_config(select_type)
            if not config:
                return

            # 获取排名范围和分数线配置
            self.rank_ranges = self._get_rank_ranges(config, district_name)
            self.score_lines = self._get_score_lines(config)

            # 构建查询条件
            query = Q(exam_id=exam_id, total_score__gt=0)

            if select_type != '未分科':
                query &= Q(select_type=select_type)

            if district_name:
                query &= Q(district_name=district_name)

            if school_name:
                query &= Q(school_name=school_name)

            # 获取成绩数据
            scores = ScoreStudentBasic.objects.filter(query)

            if not scores.exists():
                return

            # 计算统计数据
            stats = {
                'exam_id': exam_id,
                'select_type': select_type,
                'level_type': level_type,
                'district_name': district_name,
                'school_name': school_name,
                'basic_stats': self._calculate_basic_stats(scores),
                'ranking_stats': self._calculate_ranking_stats(scores),
                'score_lines': self._calculate_score_lines(scores)
            }

            # 保存统计结果
            ExamLevelStatistics.objects.update_or_create(
                exam_id=exam_id,
                select_type=select_type,
                level_type=level_type,
                district_name=district_name,
                school_name=school_name,
                defaults=stats
            )

        except Exception as e:
            logger.error(
                f"生成层级统计失败: exam_id={exam_id}, "
                f"level={level_type}, error={str(e)}"
            )
            raise

    def _calculate_basic_stats(self, scores):
        """计算基础统计"""
        try:
            return {
                'student_count': scores.count(),
                'max_score': float(scores.aggregate(Max('total_score'))['total_score__max'] or 0),
                'min_score': float(scores.aggregate(Min('total_score'))['total_score__min'] or 0),
                'mean_score': float(scores.aggregate(Avg('total_score'))['total_score__avg'] or 0),
                'std_dev': float(scores.aggregate(StdDev('total_score'))['total_score__stddev'] or 0)
            }
        except Exception as e:
            logger.error(f"计算基础统计失败: error={str(e)}")
            return {}

        # _calculate_ranking_stats 和 _calculate_score_lines 方法保持不变