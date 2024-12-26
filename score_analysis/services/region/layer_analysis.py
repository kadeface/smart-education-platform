from typing import List, Dict, Optional
from django.db import transaction
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Avg, Max, Min, StdDev, Count, F, Q
from decimal import Decimal
from score_processor.models import ScoreStudentBasic, BaseExamConfig
from score_analysis.models.region import LayerAnalysis, RegionLayerDetail
import logging
logger = logging.getLogger(__name__)
class LayerAnalysisService:
    """总分层次分析服务"""
    
    def __init__(self):
        # 市级层次配置
        self.city_layer_types = {
            '文科': ['top10', 'top50', 'top100', 'top200', 'top600', 'top3800'],
            '理科': ['top10', 'top50', 'top100', 'top200', 'top3000', 'top9500']
        }
        
        # 区县层次配置
        self.district_layer_types = {
            '文科': ['top10', 'top50', 'top100', 'top200', 'top300','top350', 'top400'],
            '理科': ['top10', 'top50', 'top100', 'top200', 'top350','top400', 'top1250']
        }
        
        # 层次学生数配置
        self.layer_student_counts = {
            '文科': {
                'top10': 10,
                'top50': 50,
                'top100': 100,  #开平市文科优分层
                'top200': 200,
                'top300': 300,
                'top350': 350,  #开平市文科本科层
                'top400': 400,
                'top600': 600,  #江门市文科优分层
                'top3800': 3800 #江门市文科本科层
            },
            '理科': {
                'top10': 10,
                'top50': 50,
                'top100': 100,
                'top200': 200,
                'top350': 350,   #开平市理科优分层
                'top400': 400,
                'top1250': 1250, #开平市理科本科层
                'top3000': 3000, #江门市理科优分层
                'top9500': 9500  #江门市理科本科层
            }
        }

    def _get_layer_types(self, exam_id: str, select_type: str) -> List[str]:
        """根据考试ID获取对应的层次类型配置"""
        # 判断是否为地市级考试
        is_city_exam = 'CITY' in exam_id.upper()

        if is_city_exam:
            return self.city_layer_types[select_type]
        else:
            return self.district_layer_types[select_type]

    def _get_student_count(self, select_type: str, layer_type: str) -> int:
        """获取层次对应的学生数量"""
        return self.layer_student_counts[select_type][layer_type]

    def _get_exam_scores(self, exam_id: str, select_type: str) -> Dict:
        """获取并预处理考试成绩数据"""
        try:
            logger.info(f"开始获取考试 {exam_id} {select_type} 的成绩数据")

            # 1. 获取总体排序后的成绩
            query = ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            ).order_by(
                '-total_score',
                '-math',
                '-chinese'
            )

            # 打印SQL查询
            logger.debug(f"成绩查询SQL: {str(query.query)}")

            # 检查数据是否存在
            count = query.count()
            logger.info(f"找到 {count} 条成绩记录")

            if count == 0:
                logger.warning(f"未找到考试 {exam_id} {select_type} 的成绩数据")
                return {}

            # 获取成绩数据
            all_scores = list(query.values(
                'student_id',
                'district_name',
                'school_name',
                'total_score',
                'math',
                'chinese'
            ))

            # 打印部分数据样本
            logger.debug(f"成绩数据样本（前3条）: {all_scores[:3]}")

            # 2. 统计区县总人数
            district_counts = ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            ).values('district_name').annotate(
                total_count=Count('id')
            )

            logger.info(f"区县统计: {list(district_counts)}")

            # 3. 统计学校总人数
            school_counts = ScoreStudentBasic.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            ).values('district_name', 'school_name').annotate(
                total_count=Count('id')
            )

            logger.info(f"学校统计数量: {school_counts.count()} 所学校")
            logger.debug(f"学校统计样本（前3所）: {list(school_counts)[:3]}")

            # 4. 构建返回数据
            result = {
                'all_scores': all_scores,
                'district_stats': {
                    item['district_name']: item['total_count']
                    for item in district_counts
                },
                'school_stats': {
                    f"{item['district_name']}_{item['school_name']}": item['total_count']
                    for item in school_counts
                }
            }

            # 打印统计信息
            logger.info(f"""数据统计:
                - 总成绩记录数: {len(all_scores)}
                - 区县数量: {len(result['district_stats'])}
                - 学校数量: {len(result['school_stats'])}
            """)

            return result

        except Exception as e:
            logger.error(f"获取考试成绩数据失败: {str(e)}", exc_info=True)
            raise

    def _generate_base_layer_analysis(self, exam_id: str, select_type: str,
                                      scores: Dict) -> List[LayerAnalysis]:
        """生成基础层次分析"""
        try:
            # 1. 删除已有的分析数据
            LayerAnalysis.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            ).delete()

            # 2. 生成新的分析数据
            layer_analyses = []
            all_scores = scores['all_scores']
            # 获取对应的层次类型配置
            layer_types = self._get_layer_types(exam_id, select_type)
            for layer_type in self.city_layer_types[select_type]:
                # 获取该层次的学生数量
                student_count = self.layer_student_counts[select_type][layer_type]

                # 获取该层次的学生成绩
                layer_students = all_scores[:student_count]

                if not layer_students:
                    continue

                # 计算统计数据
                layer_scores = [float(s['total_score']) for s in layer_students]
                mean_score = sum(layer_scores) / len(layer_scores)
                max_score = max(layer_scores)
                min_score = min(layer_scores)
                std_dev = self._calculate_std_dev(layer_scores)

                # 按学校分组统计
                school_stats = {}
                for student in layer_students:
                    school_key = f"{student['district_name']}_{student['school_name']}"
                    if school_key not in school_stats:
                        school_stats[school_key] = {
                            'district': student['district_name'],
                            'school': student['school_name'],
                            'count': 0,
                            'scores': []
                        }
                    school_stats[school_key]['count'] += 1
                    school_stats[school_key]['scores'].append(float(student['total_score']))

                # 计算每个学校的统计数据
                for stats in school_stats.values():
                    scores = stats.pop('scores')  # 删除原始分数列表
                    stats.update({
                        'mean': round(sum(scores) / len(scores), 2),
                        'max': max(scores),
                        'min': min(scores),
                        'std_dev': round(self._calculate_std_dev(scores), 2)
                    })

                # 构建JSON统计数据
                stats_data = {
                    'summary': {
                        'student_count': len(layer_scores),
                        'mean_score': round(mean_score, 2),
                        'max_score': max_score,
                        'min_score': min_score,
                        'std_dev': round(std_dev, 2)
                    },
                    'school_distribution': school_stats
                }

                # 创建层次分析对象
                layer = LayerAnalysis(
                    exam_id=exam_id,
                    select_type=select_type,
                    layer_type=layer_type,
                    student_count=len(layer_scores),
                    mean_score=Decimal(str(round(mean_score, 2))),
                    max_score=Decimal(str(max_score)),
                    min_score=Decimal(str(min_score)),
                    std_dev=Decimal(str(round(std_dev, 2))),
                    stats_data=stats_data
                )

                layer_analyses.append(layer)

            # 3. 批量保存并获取保存后的对象
            layers = LayerAnalysis.objects.bulk_create(layer_analyses)

            # 4. 重新查询以获取完整的对象（包括主键）
            layers = LayerAnalysis.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            ).order_by('layer_id')

            return list(layers)

        except Exception as e:
            logger.error(f"生成基础层次分析失败: {str(e)}", exc_info=True)
            raise
    @staticmethod
    def _calculate_std_dev(scores: List[float]) -> float:
        """
        计算标准差
        Args:
            scores: 分数列表
        Returns:
            float: 标准差
        """
        if not scores:
            return 0.0

        # 将所有分数转换为float类型
        scores = [float(score) for score in scores]
        mean = sum(scores) / len(scores)
        squared_diff_sum = sum((x - mean) ** 2 for x in scores)
        return (squared_diff_sum / len(scores)) ** 0.5

    def _generate_district_layer_details(self, layer_analyses: List[LayerAnalysis], scores: Dict) -> None:
        """生成区县层次详情"""
        try:
            # 确保有layer_id
            layer_ids = [layer.layer_id for layer in layer_analyses]
            # 1. 删除已有的区县层次详情数据
            RegionLayerDetail.objects.filter(
                layer__in=layer_analyses,
                school_name__isnull=True
            ).delete()

            # 2. 生成新的区县层次详情
            district_details = []
            all_scores = scores['all_scores']
            district_stats = scores['district_stats']

            for layer in layer_analyses:
                # 获取该层次的最低分（作为分数线）
                cutoff_score = layer.min_score

                # 按区县分组统计该层次的学生
                district_groups = {}
                for student in all_scores:
                    if student['total_score'] >= cutoff_score:
                        district = student['district_name']
                        if district not in district_groups:
                            district_groups[district] = {
                                'scores': []
                            }
                        district_groups[district]['scores'].append(float(student['total_score']))

                # 为每个区县生成详情
                for district, data in district_groups.items():
                    district_scores = data['scores']
                    district_mean = sum(district_scores) / len(district_scores)

                    detail = RegionLayerDetail(
                        layer=layer,
                        district_name=district,
                        school_name=None,  # 区县级统计
                        student_count=len(district_scores),  # 该层次学生数
                        total_student_count=district_stats[district],  # 区县总人数
                        layer_ratio=Decimal(str(round(len(district_scores) / layer.student_count * 100, 2))),  # 占层次比例
                        region_ratio=Decimal(str(round(len(district_scores) / district_stats[district] * 100, 2))),
                        # 占区县比例
                        mean_score=Decimal(str(round(district_mean, 2))),
                        max_score=Decimal(str(max(district_scores))),
                        min_score=Decimal(str(min(district_scores))),
                        std_dev=Decimal(str(round(self._calculate_std_dev(district_scores), 2))),
                        city_diff=Decimal(str(round(district_mean - float(layer.mean_score), 2))),  # 与市均差距
                        district_diff=None  # 区县统计不需要此项
                    )
                    district_details.append(detail)

            # 3. 批量保存
            RegionLayerDetail.objects.bulk_create(district_details)

        except Exception as e:
            logger.error(f"生成区县层次详情失败: {str(e)}", exc_info=True)
            raise

    def _generate_school_layer_details(self, layer_analyses: List[LayerAnalysis], scores: Dict) -> None:
        """生成学校层次详情"""
        try:
            # 确保有layer_id
            layer_ids = [layer.layer_id for layer in layer_analyses]
            # 1. 删除已有的学校层次详情数据
            RegionLayerDetail.objects.filter(
                layer__in=layer_analyses,
                school_name__isnull=False
            ).delete()

            # 2. 生成新的学校层次详情
            school_details = []
            all_scores = scores['all_scores']
            school_stats = scores['school_stats']

            # 获取区县平均分（用于计算学校与区县的差距）
            district_means = {}
            for layer in layer_analyses:
                district_means[layer.layer_id] = {}
                district_details = RegionLayerDetail.objects.filter(
                    layer=layer,
                    school_name__isnull=True
                )
                for detail in district_details:
                    district_means[layer.layer_id][detail.district_name] = float(detail.mean_score)

            for layer in layer_analyses:
                # 从layer的stats_data中获取学校分布数据
                school_distribution = layer.stats_data.get('school_distribution', {})

                for school_key, school_data in school_distribution.items():
                    district = school_data['district']
                    school = school_data['school']

                    # 获取区县平均分
                    district_mean = district_means[layer.layer_id].get(district, float(layer.mean_score))

                    detail = RegionLayerDetail(
                        layer=layer,
                        district_name=district,
                        school_name=school,
                        student_count=school_data['count'],  # 该层次学生数
                        total_student_count=school_stats[school_key],  # 学校总人数
                        layer_ratio=Decimal(str(round(school_data['count'] / layer.student_count * 100, 2))),  # 占层次比例
                        region_ratio=Decimal(str(round(school_data['count'] / school_stats[school_key] * 100, 2))),
                        # 占学校比例
                        mean_score=Decimal(str(school_data['mean'])),
                        max_score=Decimal(str(school_data['max'])),
                        min_score=Decimal(str(school_data['min'])),
                        std_dev=Decimal(str(school_data['std_dev'])),
                        city_diff=Decimal(str(round(school_data['mean'] - float(layer.mean_score), 2))),  # 与市均差距
                        district_diff=Decimal(str(round(school_data['mean'] - district_mean, 2)))  # 与区均差距
                    )
                    school_details.append(detail)

            # 3. 批量保存
            RegionLayerDetail.objects.bulk_create(school_details)

        except Exception as e:
            logger.error(f"生成学校层次详情失败: {str(e)}", exc_info=True)
            raise

    def generate_layer_analysis(self, exam_id: str) -> bool:
        """生成分层分析入口方法"""
        try:
            logger.info(f"开始生成考试 {exam_id} 的分层分析")

            # 判断是否为地市级考试
            is_city_exam = 'CITY' in exam_id.upper()
            logger.info(f"考试类型: {'地市级' if is_city_exam else '区县级'}")

            # 删除已有数据
            LayerAnalysis.objects.filter(exam_id=exam_id).delete()
            RegionLayerDetail.objects.filter(layer__exam_id=exam_id).delete()

            # 分别处理文理科
            for select_type in ['文科', '理科']:
                if is_city_exam:
                    # 地市级：处理所有层次
                    self._generate_analysis_by_type(exam_id, select_type)
                else:
                    # 区县级：只处理区县层次
                    self._generate_district_analysis(exam_id, select_type)

            return True

        except Exception as e:
            logger.error(f"生成分层分析失败: {str(e)}", exc_info=True)
            raise

    def _generate_analysis_by_type(self, exam_id: str, select_type: str) -> bool:
        """生成地市级分析"""
        try:
            logger.info(f"开始生成地市级分析: {exam_id} {select_type}")

            # 1. 获取成绩数据
            scores = self._get_exam_scores(exam_id, select_type)
            if not scores:
                logger.warning(f"未找到考试成绩数据: {exam_id} {select_type}")
                return False

            # 2. 生成基础层次分析（会自动使用市级配置）
            layer_analyses = self._generate_base_layer_analysis(
                exam_id, select_type, scores
            )

            # 3. 生成区县层次详情
            self._generate_district_layer_details(layer_analyses, scores)

            # 4. 生成学校层次详情
            self._generate_school_layer_details(layer_analyses, scores)

            logger.info(f"地市级分析生成完成: {exam_id} {select_type}")
            return True

        except Exception as e:
            logger.error(f"地市级分析生成失败: {exam_id} {select_type} - {str(e)}", exc_info=True)
            raise

    def _generate_district_analysis(self, exam_id: str, select_type: str) -> bool:
        """生成区县级分析"""
        try:
            logger.info(f"开始生成区县级分析: {exam_id} {select_type}")

            # 1. 获取成绩数据
            scores = self._get_exam_scores(exam_id, select_type)
            if not scores:
                return False

            # 2. 临时设置为区县级配置
            original_layer_types = self.city_layer_types
            self.city_layer_types = self.district_layer_types

            try:
                # 3. 生成基础层次分析
                layer_analyses = self._generate_base_layer_analysis(
                    exam_id, select_type, scores
                )

                # 4. 只生成区县层次详情
                self._generate_district_layer_details(layer_analyses, scores)

            finally:
                # 5. 恢复原始配置
                self.city_layer_types = original_layer_types

            return True

        except Exception as e:
            logger.error(f"区县级分析生成失败: {str(e)}")
            raise