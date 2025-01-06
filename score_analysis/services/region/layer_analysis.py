from typing import List, Dict, Optional
import json
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
        # 对于市级考试，返回所有层次（市级+区县）
        if 'CITY' in exam_id.upper():
            return list(set(
                self.city_layer_types[select_type] +  # 市级层次
                self.district_layer_types[select_type]  # 区县层次
            ))
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

            # 2. 生成排名
            all_scores = scores['all_scores']
            sorted_scores = sorted(all_scores,
                                   key=lambda x: (float(x['total_score']),
                                                  float(x.get('math', 0)),  # 总分相同，按数学成绩
                                                  float(x.get('chinese', 0)),  # 数学相同，按语文成绩
                                                  x['student_id']),  # 保证排序稳定性
                                   reverse=True)

            # 添加排名信息
            current_rank = 1
            current_score = None
            same_rank_count = 0

            for i, student in enumerate(sorted_scores):
                score = float(student['total_score'])
                if score != current_score:
                    current_rank = i + 1
                    current_score = score
                    same_rank_count = 1
                else:
                    same_rank_count += 1
                student['rank'] = current_rank
                student['same_rank_count'] = same_rank_count

            # 3. 生成新的分析数据
            layer_analyses = []
            layer_types = self._get_layer_types(exam_id, select_type)

            for layer_type in layer_types:
                # 获取该层次的学生数量
                student_count = self.layer_student_counts[select_type][layer_type]

                # 获取该层次的学生（按排名）
                layer_students = sorted_scores[:student_count]

                # 记录最低分和最低排名
                min_score = float(layer_students[-1]['total_score'])
                min_rank = layer_students[-1]['rank']

                # 添加同分数的学生
                while (len(sorted_scores) > student_count and
                       float(sorted_scores[student_count]['total_score']) == min_score):
                    layer_students.append(sorted_scores[student_count])
                    student_count += 1

                # 计算统计数据
                layer_scores = [float(s['total_score']) for s in layer_students]
                mean_score = sum(layer_scores) / len(layer_scores)
                max_score = max(layer_scores)
                min_score = min(layer_scores)
                std_dev = self._calculate_std_dev(layer_scores)

                # 获取最好和最差排名
                best_rank = min(s['rank'] for s in layer_students)
                worst_rank = max(s['rank'] for s in layer_students)

                # 按学校分组统计
                school_stats = {}
                for student in layer_students:
                    school_key = f"{student['district_name']}_{student['school_name']}"
                    if school_key not in school_stats:
                        school_stats[school_key] = {
                            'district': student['district_name'],
                            'school': student['school_name'],
                            'count': 0,
                            'scores': [],
                            'ranks': []
                        }
                    school_stats[school_key]['count'] += 1
                    school_stats[school_key]['scores'].append(float(student['total_score']))
                    school_stats[school_key]['ranks'].append(student['rank'])

                # 计算每个学校的统计数据
                for stats in school_stats.values():
                    scores = stats.pop('scores')
                    ranks = stats.pop('ranks')
                    stats.update({
                        'mean': round(sum(scores) / len(scores), 2),
                        'max': max(scores),
                        'min': min(scores),
                        'std_dev': round(self._calculate_std_dev(scores), 2),
                        'best_rank': min(ranks),
                        'worst_rank': max(ranks)
                    })

                # 构建JSON统计数据
                stats_data = {
                    'summary': {
                        'student_count': len(layer_scores),
                        'mean_score': round(mean_score, 2),
                        'max_score': max_score,
                        'min_score': min_score,
                        'std_dev': round(std_dev, 2),
                        'best_rank': best_rank,
                        'worst_rank': worst_rank,
                        'plan_count': self.layer_student_counts[select_type][layer_type],
                        'actual_count': len(layer_students)
                    },
                    'school_distribution': school_stats
                }

                logger.debug(f"""层次分析统计:
                    层次类型: {layer_type}
                    计划人数: {self.layer_student_counts[select_type][layer_type]}
                    实际人数: {len(layer_students)}
                    最低分: {min_score}
                    最低排名: {worst_rank}
                    最好排名: {best_rank}
                """)

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

            # 4. 批量保存并获取保存后的对象
            layers = LayerAnalysis.objects.bulk_create(layer_analyses)

            # 5. 重新查询以获取完整的对象（包括主键）
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

    def generate_layer_analysis(self, exam_id: str) -> bool:
        """生成分层分析入口方法"""
        try:
            logger.info(f"开始生成考试 {exam_id} 的分层分析")

            # 删除已有数据
            LayerAnalysis.objects.filter(exam_id=exam_id).delete()
            RegionLayerDetail.objects.filter(layer__exam_id=exam_id).delete()

            # 分别处理文理科
            for select_type in ['文科', '理科']:
                # 统一使用 _generate_analysis_by_type
                # 在 _get_layer_types 中会根据考试ID返回对应的层次配置
                self._generate_analysis_by_type(exam_id, select_type)

            logger.info(f"考试 {exam_id} 的分层分析生成完成")
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

            # 2. 生成基础层次分析
            layer_analyses = self._generate_base_layer_analysis(
                exam_id, select_type, scores
            )

            # 3. 生成区县层次详情（包含学校统计）
            self._generate_district_layer_details(layer_analyses, scores)

            logger.info(f"地市级分析生成完成: {exam_id} {select_type}")
            return True

        except Exception as e:
            logger.error(f"地市级分析生成失败: {exam_id} {select_type} - {str(e)}", exc_info=True)
            raise

    def _generate_district_layer_details(self, layer_analyses: List[LayerAnalysis], scores: Dict) -> None:
        """生成区县层次详情"""
        try:
            print(f"开始处理，原始层次数量: {len(layer_analyses)}")

            # 1. 删除已有的区县层次详情数据
            RegionLayerDetail.objects.filter(
                layer__in=layer_analyses
            ).delete()

            # 2. 获取科类和区县层次配置
            select_type = layer_analyses[0].select_type
            district_layers = self.district_layer_types[select_type]

            print(f"""
                层次信息:
                - 原始层次: {[layer.layer_type for layer in layer_analyses]}
                - 区县层次: {district_layers}
            """)

            # 3. 生成总排名
            sorted_scores = sorted(scores['all_scores'],
                                   key=lambda x: (float(x['total_score']),
                                                  float(x.get('math', 0)),
                                                  float(x.get('chinese', 0)),
                                                  x['student_id']),
                                   reverse=True)

            # 4. 添加排名信息
            current_rank = 1
            current_score = None
            for i, student in enumerate(sorted_scores):
                score = float(student['total_score'])
                if score != current_score:
                    current_rank = i + 1
                    current_score = score
                student['rank'] = current_rank

            # 5. 按区县分组所有学生
            district_all_scores = {}
            for student in sorted_scores:
                district = student['district_name']
                if district not in district_all_scores:
                    district_all_scores[district] = []
                district_all_scores[district].append(student)

            # 6. 计算每个区县的实际层次
            district_details = []

            for district, district_scores in district_all_scores.items():
                print(f"\n处理区县: {district}")
                total_students = len(district_scores)

                # 按成绩排序区县学生
                district_sorted_scores = sorted(district_scores,
                                                key=lambda x: (float(x['total_score']),
                                                               float(x.get('math', 0)),
                                                               float(x.get('chinese', 0))),
                                                reverse=True)

                # 处理每个层次
                for layer_type in district_layers:
                    # 获取该层次的学生数量
                    student_count = self.layer_student_counts[select_type][layer_type]

                    print(f"  层次 {layer_type}: 总人数 {total_students}, 计划人数 {student_count}")

                    if student_count >= total_students:
                        print(f"    跳过：计划人数 {student_count} 大于等于区县总人数 {total_students}")
                        continue

                    # 获取该层次的学生
                    layer_students = district_sorted_scores[:student_count]

                    # 处理同分进档
                    if layer_students:
                        min_score = float(layer_students[-1]['total_score'])
                        while (len(district_sorted_scores) > student_count and
                               float(district_sorted_scores[student_count]['total_score']) == min_score):
                            layer_students.append(district_sorted_scores[student_count])
                            student_count += 1

                    # 按学校分组
                    school_groups = {}
                    for student in layer_students:
                        school = student['school_name']
                        if school not in school_groups:
                            school_groups[school] = {
                                'scores': [],
                                'ranks': [],
                                'student_count': 0
                            }

                        school_groups[school]['scores'].append(float(student['total_score']))
                        school_groups[school]['ranks'].append(student['rank'])
                        school_groups[school]['student_count'] += 1

                    # 计算层次平均分
                    layer_mean = Decimal(
                        str(sum(float(s['total_score']) for s in layer_students) / len(layer_students)))

                    # 生成学校统计数据
                    school_stats = {}
                    for school, data in school_groups.items():
                        school_scores = data['scores']
                        school_mean = Decimal(str(sum(school_scores) / len(school_scores)))

                        school_stats[school] = {
                            'student_count': data['student_count'],
                            'total_student_count': len([s for s in district_scores if s['school_name'] == school]),
                            'mean_score': float(round(school_mean, 2)),
                            'max_score': float(max(school_scores)),
                            'min_score': float(min(school_scores)),
                            'best_rank': min(data['ranks']),
                            'worst_rank': max(data['ranks']),
                            'std_dev': float(round(Decimal(str(self._calculate_std_dev(school_scores))), 2)),
                            'ratio': float(round(Decimal(str(data['student_count'])) /
                                                 Decimal(str(len([s for s in district_scores if
                                                                  s['school_name'] == school]))) * 100, 2)),
                            'city_diff': float(round(school_mean - layer_mean, 2)),
                            'district_diff': float(round(school_mean - layer_mean, 2))
                        }

                    # 添加区县排名信息
                    all_ranks = [r for data in school_groups.values() for r in data['ranks']]
                    school_stats['district_ranks'] = {
                        'best_rank': min(all_ranks) if all_ranks else 0,
                        'worst_rank': max(all_ranks) if all_ranks else 0
                    }

                    # 找到对应的 LayerAnalysis 对象
                    layer_analysis = next(
                        (l for l in layer_analyses if l.layer_type == layer_type),
                        None
                    )

                    if not layer_analysis:
                        print(f"    跳过：未找到层次分析对象 {layer_type}")
                        continue

                    # 创建区县层次详情记录
                    detail = RegionLayerDetail(
                        layer=layer_analysis,
                        district_name=district,
                        student_count=len(layer_students),
                        total_student_count=total_students,
                        layer_ratio=round(Decimal(str(len(layer_students))) / Decimal(str(total_students)) * 100, 2),
                        region_ratio=round(Decimal(str(len(layer_students))) / Decimal(str(total_students)) * 100, 2),
                        mean_score=round(layer_mean, 2),
                        max_score=Decimal(str(max(float(s['total_score']) for s in layer_students))),
                        min_score=Decimal(str(min(float(s['total_score']) for s in layer_students))),
                        std_dev=round(
                            Decimal(str(self._calculate_std_dev([float(s['total_score']) for s in layer_students]))),
                            2),
                        city_diff=Decimal('0.00'),  # 这个值会在后面更新
                        district_diff=Decimal('0.00'),
                        school_stats=school_stats
                    )
                    district_details.append(detail)

                    print(f"    实际入选人数: {len(layer_students)}, 学校数量: {len(school_groups)}")

            # 7. 计算市级差异
            for layer_type in set(d.layer.layer_type for d in district_details):
                layer_details = [d for d in district_details if d.layer.layer_type == layer_type]
                if layer_details:
                    city_mean = sum(float(d.mean_score) for d in layer_details) / len(layer_details)
                    for detail in layer_details:
                        detail.city_diff = round(float(detail.mean_score) - city_mean, 2)

            # 8. 批量保存
            created = RegionLayerDetail.objects.bulk_create(district_details)
            print(f"\n总共创建记录数: {len(created)}")

            return True

        except Exception as e:
            print(f"错误: {str(e)}")
            logger.error(f"生成区县层次详情失败: {str(e)}", exc_info=True)
            raise