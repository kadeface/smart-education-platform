from django.db.models import Max,Min,Avg

from score_analysis.models import BaseExamConfig, ScoreStudentBasic, BaseSubjectConfig
from score_analysis.models.statistics import StatisticsExamIndicators

import logging
logger = logging.getLogger(__name__)

class StatisticsGenerator:
    """统计数据生成器"""

    def generate_exam_statistics(self, exam_id):
        """生成考试统计数据
        Args:
            exam_id: 考试ID
        """
        try:
            exam_config = BaseExamConfig.objects.get(id=exam_id)
            is_division = self._is_division_exam(exam_config)

            # 1. 生成市级统计
            self._generate_city_statistics(exam_id, is_division)

            # 2. 生成区县级统计
            districts = self._get_districts(exam_id)
            for district in districts:
                self._generate_district_statistics(exam_id, district, is_division)

            logger.info(f"考试统计数据生成完成: exam_id={exam_id}")

        except Exception as e:
            logger.error(f"生成考试统计数据失败: exam_id={exam_id}, error={str(e)}")
            logger.exception("详细错误信息:")
            raise

    def _is_division_exam(self, exam_config):
        """判断是否为分科考试"""
        return (exam_config.exam_id.endswith('-H-') and
                exam_config.semester not in ['高一上'])

    def _get_districts(self, exam_id):
        """获取考试涉及的区县列表"""
        return ScoreStudentBasic.objects.filter(
            exam_id=exam_id
        ).values_list('district_name', flat=True).distinct()

    def _generate_city_statistics(self, exam_id, is_division):
        """生成市级统计数据"""
        # 获取基础查询集
        base_query = ScoreStudentBasic.objects.filter(exam_id=exam_id)

        if is_division:
            # 分科统计
            for select_type in ['文科', '理科']:
                scores = base_query.filter(select_type=select_type)
                if scores.exists():
                    # 生成总分统计
                    self._generate_total_statistics(
                        exam_id=exam_id,
                        scores=scores,
                        level_type='city',
                        select_type=select_type
                    )
                    # 生成各科统计
                    self._generate_subject_statistics(
                        exam_id=exam_id,
                        scores=scores,
                        level_type='city',
                        select_type=select_type
                    )
        else:
            # 不分科统计
            # 生成总分统计
            self._generate_total_statistics(
                exam_id=exam_id,
                scores=base_query,
                level_type='city'
            )
            # 生成各科统计
            self._generate_subject_statistics(
                exam_id=exam_id,
                scores=base_query,
                level_type='city'
            )

    def _generate_district_statistics(self, exam_id, district, is_division):
        """生成区县级统计数据"""
        # 获取区县数据
        base_query = ScoreStudentBasic.objects.filter(
            exam_id=exam_id,
            district_name=district
        )

        if is_division:
            for select_type in ['文科', '理科']:
                scores = base_query.filter(select_type=select_type)
                if scores.exists():
                    self._generate_total_statistics(
                        exam_id=exam_id,
                        scores=scores,
                        level_type='district',
                        district_name=district,
                        select_type=select_type
                    )
                    self._generate_subject_statistics(
                        exam_id=exam_id,
                        scores=scores,
                        level_type='district',
                        district_name=district,
                        select_type=select_type
                    )
        else:
            self._generate_total_statistics(
                exam_id=exam_id,
                scores=base_query,
                level_type='district',
                district_name=district
            )
            self._generate_subject_statistics(
                exam_id=exam_id,
                scores=base_query,
                level_type='district',
                district_name=district
            )

    def _generate_total_statistics(self, exam_id, scores, level_type, district_name=None, select_type=None):
        """生成总分统计数据"""
        # 计算基础统计指标
        stats = {
            'exam_id': exam_id,
            'level_type': level_type,
            'select_type': select_type or '未分科',
            'student_count': scores.count(),
            'max_score': scores.aggregate(Max('total_score'))['total_score__max'],
            'min_score': scores.aggregate(Min('total_score'))['total_score__min'],
            'mean_score': scores.aggregate(Avg('total_score'))['total_score__avg'],
        }

        if district_name:
            stats['district_name'] = district_name

        # 计算四分位数
        scores_list = list(scores.values_list('total_score', flat=True))
        stats.update(self._calculate_quantiles(scores_list))

        # 计算及格率等
        stats.update(self._calculate_rates(scores_list))

        # 计算学校分布
        stats['school_distribution'] = self._calculate_school_distribution(scores)

        # 计算排名分布
        stats['rank_distribution'] = self._calculate_rank_distribution(scores)

        # 计算分数线达线情况
        stats['threshold_stats'] = self._calculate_threshold_stats(scores)

        # 保存或更新统计数据
        StatisticsExamIndicators.objects.update_or_create(
            exam_id=exam_id,
            level_type=level_type,
            district_name=district_name,
            select_type=select_type or '未分科',
            subject__isnull=True,
            defaults=stats
        )

    def _generate_subject_statistics(self, exam_id, scores, level_type, district_name=None, select_type=None):
        """生成学科统计数据"""
        # 获取考试科目
        subjects = BaseSubjectConfig.objects.filter(exam_id=exam_id)

        for subject in subjects:
            # 获取科目成绩
            subject_scores = [
                score.subject_scores.get(subject.code, 0)
                for score in scores
            ]

            if not subject_scores:
                continue

            # 计算科目统计数据
            stats = {
                'exam_id': exam_id,
                'subject': subject,
                'level_type': level_type,
                'select_type': select_type or '未分科',
                'student_count': len(subject_scores),
                'max_score': max(subject_scores),
                'min_score': min(subject_scores),
                'mean_score': sum(subject_scores) / len(subject_scores)
            }

            if district_name:
                stats['district_name'] = district_name

            # 计算四分位数
            stats.update(self._calculate_quantiles(subject_scores))

            # 计算及格率等
            stats.update(self._calculate_rates(subject_scores))

            # 保存或更新统计数据
            StatisticsExamIndicators.objects.update_or_create(
                exam_id=exam_id,
                subject=subject,
                level_type=level_type,
                district_name=district_name,
                select_type=select_type or '未分科',
                defaults=stats
            )

    def _calculate_quantiles(self, scores):
        """计算四分位数
        Args:
            scores: 分数列表
        Returns:
            dict: 四分位数统计
        """
        try:
            if not scores:
                return {
                    'q80_score': 0,
                    'median_score': 0,
                    'q20_score': 0,
                    'q10_score': 0
                }

            scores = sorted([s for s in scores if s > 0])  # 排除无效成绩
            if not scores:
                return {
                    'q80_score': 0,
                    'median_score': 0,
                    'q20_score': 0,
                    'q10_score': 0
                }

            n = len(scores)
            return {
                'q80_score': scores[int(n * 0.8)] if n > 0 else 0,
                'median_score': scores[int(n * 0.5)] if n > 0 else 0,
                'q20_score': scores[int(n * 0.2)] if n > 0 else 0,
                'q10_score': scores[int(n * 0.1)] if n > 0 else 0
            }
        except Exception as e:
            logger.error(f"计算四分位数失败: error={str(e)}")
            return {
                'q80_score': 0,
                'median_score': 0,
                'q20_score': 0,
                'q10_score': 0
            }

    def _calculate_rates(self, scores, excellent_threshold=0.85, pass_threshold=0.60, low_threshold=0.30):
        """计算及格率等
        Args:
            scores: 分数列表
            excellent_threshold: 优秀线比例
            pass_threshold: 及格线比例
            low_threshold: 低分线比例
        Returns:
            dict: 比率统计
        """
        try:
            if not scores:
                return {
                    'excellent_rate': 0,
                    'pass_rate': 0,
                    'low_score_rate': 0
                }

            valid_scores = [s for s in scores if s > 0]
            if not valid_scores:
                return {
                    'excellent_rate': 0,
                    'pass_rate': 0,
                    'low_score_rate': 0
                }

            max_score = max(valid_scores)
            excellent_line = max_score * excellent_threshold
            pass_line = max_score * pass_threshold
            low_line = max_score * low_threshold

            total = len(valid_scores)
            return {
                'excellent_rate': round(sum(1 for s in valid_scores if s >= excellent_line) * 100 / total, 2),
                'pass_rate': round(sum(1 for s in valid_scores if s >= pass_line) * 100 / total, 2),
                'low_score_rate': round(sum(1 for s in valid_scores if s <= low_line) * 100 / total, 2)
            }
        except Exception as e:
            logger.error(f"计算比率失败: error={str(e)}")
            return {
                'excellent_rate': 0,
                'pass_rate': 0,
                'low_score_rate': 0
            }

    def _calculate_school_distribution(self, scores):
        """计算学校分布
        Args:
            scores: QuerySet of ScoreStudentBasic
        Returns:
            dict: {school_name: {count, mean_score, max_score, ...}}
        """
        try:
            distribution = {}

            # 按学校分组统计
            school_stats = scores.values('school_name').annotate(
                count=Count('id'),
                mean_score=Avg('total_score'),
                max_score=Max('total_score'),
                min_score=Min('total_score')
            )

            for stat in school_stats:
                school_scores = scores.filter(
                    school_name=stat['school_name']
                ).values_list('total_score', flat=True)

                # 计算学校的四分位数和比率
                quantiles = self._calculate_quantiles(list(school_scores))
                rates = self._calculate_rates(list(school_scores))

                distribution[stat['school_name']] = {
                    'count': stat['count'],
                    'mean_score': round(float(stat['mean_score'] or 0), 2),
                    'max_score': float(stat['max_score'] or 0),
                    'min_score': float(stat['min_score'] or 0),
                    **quantiles,
                    **rates
                }

            return distribution

        except Exception as e:
            logger.error(f"计算学校分布失败: error={str(e)}")
            return {}

    def _calculate_rank_distribution(self, scores):
        """计算排名分布
        Args:
            scores: QuerySet of ScoreStudentBasic
        Returns:
            dict: {school_name: {top_10: n, top_20: n, ...}}
        """
        try:
            # 定义要统计的名次范围
            rank_ranges = [10, 20, 50, 100, 200, 500]
            distribution = {}

            # 获取排序后的成绩
            ordered_scores = scores.order_by('-total_score')
            total_count = ordered_scores.count()

            for rank_n in rank_ranges:
                if rank_n > total_count:
                    continue

                # 获取前N名的学校分布
                top_n_schools = ordered_scores[:rank_n].values('school_name')
                school_counts = Counter(s['school_name'] for s in top_n_schools)

                # 更新每个学校的排名统计
                for school, count in school_counts.items():
                    if school not in distribution:
                        distribution[school] = {}
                    distribution[school][f'top_{rank_n}'] = count

            return distribution

        except Exception as e:
            logger.error(f"计算排名分布失败: error={str(e)}")
            return {}

    def _calculate_threshold_stats(self, scores):
        """计算分数线达线情况
        Args:
            scores: QuerySet of ScoreStudentBasic
        Returns:
            dict: {line_type: {line, count, rate}}
        """
        try:
            # 获取分数线
            exam_id = scores.first().exam_id
            select_type = scores.first().select_type

            score_lines = ExamScoreLines.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            )

            if not score_lines.exists():
                return {}

            # 计算达线统计
            stats = {}
            total_count = scores.filter(total_score__gt=0).count()

            for line in score_lines:
                above_count = scores.filter(
                    total_score__gt=0,
                    total_score__gte=line.score
                ).count()

                stats[line.line_type] = {
                    'line': float(line.score),
                    'count': above_count,
                    'rate': round(above_count * 100 / total_count, 2) if total_count > 0 else 0
                }

            return stats

        except Exception as e:
            logger.error(f"计算分数线统计失败: error={str(e)}")
            return {}