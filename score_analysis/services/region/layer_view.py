# score_analysis/services/layer_view.py

from django.db.models import  Count
from score_analysis.models.region import LayerAnalysis, RegionLayerDetail
from score_processor.models import ScoreStudentBasic
import logging
from score_processor.models import BaseExamConfig
logger = logging.getLogger(__name__)


class LayerViewService:
    """层次分析视图服务类"""

    def get_exam_info(self, exam_id: str) -> dict:
        """获取考试基本信息"""
        """获取考试基本信息"""
        try:
            print("\n=== get_exam_info 调试信息 ===")

            # 从 ScoreStudentBasic 表获取每个科类的总人数
            total_students = ScoreStudentBasic.objects.filter(
                exam_id=exam_id
            ).values('select_type').annotate(
                total=Count('student_id')
            )

            print(f"查询SQL: {total_students.query}")
            print(f"原始数据: {list(total_students)}")

            result = {
                'exam_id': exam_id,
                'exam_name': self._get_exam_name(exam_id),
                'total_students': {
                    item['select_type']: item['total']
                    for item in total_students
                }
            }

            print(f"返回结果: {result}")
            print("=== get_exam_info 结束 ===\n")

            return result

        except Exception as e:
            logger.error(f"获取考试信息失败: {str(e)}", exc_info=True)
            return {
                'exam_id': exam_id,
                'exam_name': exam_id,
                'total_students': {'理科': 0, '文科': 0}
            }

    # score_analysis/services/layer_view.py

    # score_analysis/services/layer_view.py

    def get_district_analysis(self, exam_id: str, select_type: str) -> dict:
        """获取区县层次分析数据"""
        try:
            print("\n=== get_district_analysis 调试信息 ===")

            # 只需要获取 LayerAnalysis 的数据
            layer_analyses = LayerAnalysis.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            ).values(
                'layer_type',
                'mean_score',
                'min_score',
                'stats_data'
            ).order_by('layer_type')

            # 格式化市级数据和区县数据
            formatted_city_stats = {}
            formatted_district_stats = {}

            for analysis in layer_analyses:
                layer_type = analysis['layer_type']
                stats_data = analysis['stats_data']

                if not stats_data:
                    continue

                # 市级统计
                formatted_city_stats[layer_type] = {
                    'avg_score': float(analysis['mean_score']),
                    'min_score': float(analysis['min_score'])
                }

                # 获取该层次的总人数
                total_students = stats_data['summary']['student_count']

                # 按区县统计数据
                district_stats = {}
                for school_data in stats_data['school_distribution'].values():
                    district = school_data['district']
                    count = school_data['count']
                    mean_score = school_data['mean']

                    if district not in district_stats:
                        district_stats[district] = {
                            'count': 0,
                            'total_score': 0
                        }

                    district_stats[district]['count'] += count
                    district_stats[district]['total_score'] += mean_score * count

                # 计算每个区县的统计数据
                for district, data in district_stats.items():
                    if district not in formatted_district_stats:
                        formatted_district_stats[district] = {}
                    district_avg_score = data['total_score'] / data['count'] if data['count'] > 0 else 0
                    city_avg_score = formatted_city_stats[layer_type]['avg_score']
                    formatted_district_stats[district][layer_type] = {
                        'count': data['count'],
                        'ratio': (data['count'] / total_students * 100) if total_students > 0 else 0,
                        'avg_score': data['total_score'] / data['count'] if data['count'] > 0 else 0,
                        'diff':  district_avg_score - city_avg_score
                    }

            print("\n格式化后的数据:")
            print(f"市级统计: {formatted_city_stats}")
            print(f"区县统计: {formatted_district_stats}")

            return {
                'city_stats': formatted_city_stats,
                'district_stats': formatted_district_stats
            }

        except Exception as e:
            print(f"\n发生错误:")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            logger.error(f"获取区县分析失败: {str(e)}", exc_info=True)
            return {'city_stats': {}, 'district_stats': {}}

    def get_school_analysis(self, exam_id: str, select_type: str, selected_districts: list = None) -> dict:
        """获取学校层次分析数据"""
        try:
            print("\n=== get_school_analysis 调试信息 ===")
            school_analysis = {}

            # 1. 处理市级数据
            city_layers = LayerAnalysis.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            ).values('layer_type', 'stats_data')

            print(f"\n1. 市级数据查询结果数: {len(city_layers)}")

            for layer in city_layers:
                print(f"\n层次类型: {layer['layer_type']}")
                stats = layer['stats_data']

                if not stats or 'school_distribution' not in stats:
                    continue

                for school_data in stats['school_distribution'].values():
                    school_name = school_data['school']
                    district = school_data['district']

                    if selected_districts and district not in selected_districts:
                        continue

                    if school_name not in school_analysis:
                        school_analysis[school_name] = {
                            'school_name': school_name,
                            'district': district,
                            'layers': {}
                        }

                    school_analysis[school_name]['layers'][layer['layer_type']] = {
                        'city': school_data['count'],
                        'district': '-'
                    }

            # 2. 处理区县数据
            layer_mappings = LayerAnalysis.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            ).values('layer_id', 'layer_type')

            layer_type_map = {item['layer_id']: item['layer_type'] for item in layer_mappings}
            layer_ids = layer_type_map.keys()

            district_layers = RegionLayerDetail.objects.filter(
                layer_id__in=layer_ids
            ).values(
                'layer_id',
                'district_name',
                'school_stats'
            )

            print(f"\n2. 区县数据查询结果数: {len(district_layers)}")

            for layer in district_layers:
                layer_type = layer_type_map[layer['layer_id']]
                district = layer['district_name']
                stats = layer['school_stats']

                for school_name, school_data in stats.items():
                    if school_name == 'district_ranks':
                        continue

                    if selected_districts and district not in selected_districts:
                        continue

                    if school_name not in school_analysis:
                        school_analysis[school_name] = {
                            'school_name': school_name,
                            'district': district,
                            'layers': {}
                        }

                    if layer_type not in school_analysis[school_name]['layers']:
                        school_analysis[school_name]['layers'][layer_type] = {
                            'city': '-',
                            'district': school_data['student_count']
                        }
                    else:
                        # 保持市级数据不变，只更新区县数据
                        current_layer = school_analysis[school_name]['layers'][layer_type]
                        school_analysis[school_name]['layers'][layer_type] = {
                            'city': current_layer.get('city', '-'),
                            'district': school_data['student_count']
                        }

            # 3. 转换为列表并排序
            result = list(school_analysis.values())

            def sort_key(school):
                layers = school.get('layers', {})
                top10_data = layers.get('top10', {})
                district_count = top10_data.get('district', '-')

                if district_count == '-':
                    count = -1
                else:
                    count = int(district_count)

                return (-count, school['district'], school['school_name'])

            result.sort(key=sort_key)

            print(f"\n最终结果:")
            print(f"学校总数: {len(result)}")
            for school in result:
                print(f"\n学校: {school['school_name']}")
                print(f"区县: {school['district']}")
                print(f"层次数据: {school['layers']}")

            return result

        except Exception as e:
            print(f"\n发生错误:")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            logger.error(f"获取学校分析失败: {str(e)}", exc_info=True)
            return []
    def _process_district_data(self, district_layer_data, selected_districts):
        """处理区县考试数据"""
        school_analysis = {}

        for layer in district_layer_data:
            layer_type = layer['layer_type']
            district = layer['district']
            stats = layer['stats_data']

            if selected_districts and district not in selected_districts:
                continue

            for school_name, school_data in stats.items():
                if school_name == 'district_ranks':  # 跳过汇总数据
                    continue

                if school_name not in school_analysis:
                    school_analysis[school_name] = {
                        'school_name': school_name,
                        'district': district,
                        'layers': {}
                    }

                school_analysis[school_name]['layers'][layer_type] = {
                    'city': '-',  # 区县考试时市级数据为 -
                    'district': school_data['student_count']
                }

        return school_analysis

    def _process_city_data(self, city_layer_data, district_layer_data, selected_districts):
        """处理市级考试数据"""
        school_analysis = {}

        # 处理市级层次数据
        for layer in city_layer_data:
            layer_type = layer['layer_type']
            stats = layer['stats_data']

            if not stats or 'school_distribution' not in stats:
                continue

            for school_data in stats['school_distribution'].values():
                school_name = school_data['school']
                district = school_data['district']

                if selected_districts and district not in selected_districts:
                    continue

                if school_name not in school_analysis:
                    school_analysis[school_name] = {
                        'school_name': school_name,
                        'district': district,
                        'layers': {}
                    }

                if layer_type not in school_analysis[school_name]['layers']:
                    school_analysis[school_name]['layers'][layer_type] = {
                        'city': school_data['count'],
                        'district': '-'  # 默认区县数据为 -
                    }

        # 处理区县层次数据
        for layer in district_layer_data:
            layer_type = layer['layer_type']
            district = layer['district']
            stats = layer['stats_data']

            for school_name, school_data in stats.items():
                if school_name == 'district_ranks':
                    continue

                if school_name in school_analysis:
                    if layer_type not in school_analysis[school_name]['layers']:
                        school_analysis[school_name]['layers'][layer_type] = {
                            'city': '-',
                            'district': school_data['student_count']
                        }
                    else:
                        school_analysis[school_name]['layers'][layer_type]['district'] = school_data['student_count']

        return school_analysis


    def _format_city_stats(self, city_stats) -> dict:
        """格式化市级统计数据"""
        result = {}
        try:
            total = sum(item['count'] for item in city_stats)
            for item in city_stats:
                layer_type = item['layer_type']
                result[layer_type] = {
                    'ratio': item['count'] / total if total > 0 else 0,
                    'avg_score': item['avg_score'],
                    'min_score': item['min_score']
                }
        except Exception as e:
            logger.error(f"格式化市级统计失败: {str(e)}", exc_info=True)
        return result

    def _format_district_stats(self, district_stats) -> dict:
        """格式化区县统计数据"""
        result = {}
        try:
            for item in district_stats:
                district = item['district_name']
                layer_type = item['layer__layer_type']

                if district not in result:
                    result[district] = {}

                result[district][layer_type] = {
                    'count': item['student_count'],
                    'ratio': item['region_ratio'],
                    'avg_score': item['mean_score']
                }
        except Exception as e:
            logger.error(f"格式化区县统计失败: {str(e)}", exc_info=True)
        return result

    def _format_school_stats(self, school_stats) -> dict:
        """格式化学校统计数据"""
        result = {}
        try:
            for item in school_stats:
                school = item['school_name']
                layer_type = item['layer__layer_type']

                if school not in result:
                    result[school] = {
                        'district': item['district_name'],
                        'layers': {}
                    }

                result[school]['layers'][layer_type] = {
                    'count': item['student_count'],
                    'avg_score': item['mean_score']
                }
        except Exception as e:
            logger.error(f"格式化学校统计失败: {str(e)}", exc_info=True)
        return result

    def _get_exam_name(self, exam_id: str) -> str:
        """从考试ID生成考试名称"""
        try:
            year = exam_id[:4]
            month = exam_id[4:6]
            exam_type = '全市统考' if 'CITY' in exam_id.upper() else f"{exam_id.split('-')[1]}区统考"
            return f"{year}年{month}月{exam_type}"
        except Exception as e:
            logger.error(f"生成考试名称失败: {str(e)}", exc_info=True)
            return exam_id

    def get_layer_types(self, exam_id: str, select_type: str) -> list:
        """获取层次类型列表"""
        try:
            # 获取所有层次类型
            layer_types = LayerAnalysis.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            ).values_list('layer_type', flat=True).distinct()

            # 自定义排序函数
            def sort_key(layer_type: str) -> int:
                # 提取数字部分
                num = int(''.join(filter(str.isdigit, layer_type)))
                return num

            # 对层次类型进行排序
            sorted_types = sorted(layer_types, key=sort_key)

            print(f"排序后的层次类型: {sorted_types}")  # 调试输出
            return sorted_types

        except Exception as e:
            logger.error(f"获取层次类型列表失败: {str(e)}", exc_info=True)
            return []


    def get_district_ranks(self, exam_id: str, select_type: str) -> dict:
        """获取区县排名信息"""
        try:
            ranks = {}
            layer_details = RegionLayerDetail.objects.filter(
                layer__exam_id=exam_id,
                layer__select_type=select_type
            ).values('district_name', 'layer__layer_type', 'district_ranks')

            for detail in layer_details:
                district = detail['district_name']
                layer_type = detail['layer__layer_type']
                if district not in ranks:
                    ranks[district] = {}
                ranks[district][layer_type] = detail['district_ranks'].get('best_rank', 0)

            return ranks
        except Exception as e:
            logger.error(f"获取区县排名失败: {str(e)}", exc_info=True)
            return {}

    def get_all_districts(self, exam_id: str) -> list:
        """获取所有区县列表"""
        try:
            return RegionLayerDetail.objects.filter(
                layer__exam_id=exam_id,
                school_name__isnull=True
            ).values_list('district_name', flat=True).distinct().order_by('district_name')
        except Exception as e:
            logger.error(f"获取区县列表失败: {str(e)}", exc_info=True)
            return []

    def _is_stream_divided(self, exam_id: str) -> bool:
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