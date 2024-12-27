# score_analysis/services/layer_view.py

from django.db.models import Avg, Count, Min, Sum
from score_analysis.models.region import LayerAnalysis, RegionLayerDetail
from score_processor.models import ScoreStudentBasic
import logging

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

    def get_district_analysis(self, exam_id: str, select_type: str) -> dict:
        """获取区县层次分析数据"""
        try:
            print("\n=== get_district_analysis 调试信息 ===")

            # 获取市级统计
            city_stats = LayerAnalysis.objects.filter(
                exam_id=exam_id,
                select_type=select_type
            ).values(
                'layer_type',
                'student_count',
                'mean_score',
                'min_score'
            ).order_by('layer_type')

            # 转换为列表以便调试
            city_stats_list = list(city_stats)
            print(f"市级统计原始数据: {city_stats_list}")

            # 获取区县统计
            district_stats = RegionLayerDetail.objects.filter(
                layer__exam_id=exam_id,
                layer__select_type=select_type,
                school_name__isnull=True
            ).values(
                'district_name',
                'layer__layer_type',
                'student_count',
                'mean_score',
                'region_ratio'
            ).order_by('district_name', 'layer__layer_type')

            # 转换为列表以便调试
            district_stats_list = list(district_stats)
            print(f"区县统计原始数据: {district_stats_list}")

            # 格式化数据
            formatted_city_stats = {}
            total_students = sum(stat['student_count'] for stat in city_stats_list)

            for stat in city_stats_list:
                formatted_city_stats[stat['layer_type']] = {
                    'count': stat['student_count'],
                    'ratio': float(stat['student_count']) / total_students if total_students > 0 else 0,
                    'avg_score': float(stat['mean_score']),
                    'min_score': float(stat['min_score'])
                }

            # 格式化区县数据
            formatted_district_stats = {}
            for stat in district_stats_list:
                district = stat['district_name']
                layer = stat['layer__layer_type']

                if district not in formatted_district_stats:
                    formatted_district_stats[district] = {}

                formatted_district_stats[district][layer] = {
                    'count': stat['student_count'],
                    'ratio': float(stat['region_ratio']),
                    'avg_score': float(stat['mean_score'])
                }

            print("\n格式化后的数据:")
            print(f"市级统计: {formatted_city_stats}")
            print(f"区县统计: {formatted_district_stats}")

            return {
                'city_stats': formatted_city_stats,
                'district_stats': formatted_district_stats
            }

        except Exception as e:
            print(f"错误详情: {str(e)}")
            print(f"city_stats: {city_stats_list if 'city_stats_list' in locals() else 'Not available'}")
            print(f"district_stats: {district_stats_list if 'district_stats_list' in locals() else 'Not available'}")
            logger.error(f"获取区县分析失败: {str(e)}", exc_info=True)
            return {'city_stats': {}, 'district_stats': {}}

    def get_school_analysis(self, exam_id: str, select_type: str, districts: list = None) -> dict:
        """获取学校层次分析数据"""
        try:
            print("\n=== get_school_analysis 调试信息 ===")
            print(f"参数: exam_id={exam_id}, select_type={select_type}, districts={districts}")

            # 构建基础查询
            query = RegionLayerDetail.objects.filter(
                layer__exam_id=exam_id,
                layer__select_type=select_type,
                school_name__isnull=False  # 只获取学校级数据
            )

            # 如果指定了区县，添加筛选条件
            if districts:
                query = query.filter(district_name__in=districts)
                print(f"应用区县筛选: {districts}")

            # 获取学校统计数据
            school_stats = query.values(
                'school_name',
                'district_name',
                'layer__layer_type',
                'student_count',
                'mean_score',
                'region_ratio'
            ).order_by('district_name', 'school_name', 'layer__layer_type')

            # 转换为列表以便调试
            school_stats_list = list(school_stats)
            print(f"\nSQL查询: {query.query}")
            print(f"原始数据数量: {len(school_stats_list)}")
            print(f"原始数据示例: {school_stats_list[:2] if school_stats_list else '无数据'}")

            # 格式化数据
            formatted_stats = self._format_school_stats(school_stats_list)
            print(f"\n格式化后的数据:")
            print(f"学校数量: {len(formatted_stats)}")
            print(f"数据示例: {dict(list(formatted_stats.items())[:1]) if formatted_stats else '无数据'}")

            return formatted_stats

        except Exception as e:
            print(f"\n获取学校分析数据时出错:")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            import traceback
            print(f"错误堆栈:\n{traceback.format_exc()}")
            logger.error(f"获取学校分析失败: {str(e)}", exc_info=True)
            return {}

    def _format_school_stats(self, school_stats) -> dict:
        """格式化学校统计数据"""
        print("\n=== _format_school_stats 调试信息 ===")
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
                    'avg_score': float(item['mean_score']),
                    'ratio': float(item['region_ratio'])
                }

            print(f"格式化完成，学校数量: {len(result)}")
            if result:
                print(f"第一个学校的数据示例: {next(iter(result.items()))}")

            return result

        except Exception as e:
            print(f"格式化学校统计数据时出错:")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            print(f"问题数据: {school_stats[:1] if school_stats else '无数据'}")
            raise  # 向上传递异常以便完整记录

    def get_all_districts(self, exam_id: str) -> list:
        """获取考试涉及的所有区县"""
        try:
            districts = RegionLayerDetail.objects.filter(
                layer__exam_id=exam_id
            ).values_list('district_name', flat=True).distinct()
            return list(districts)
        except Exception as e:
            logger.error(f"获取区县列表失败: {str(e)}", exc_info=True)
            return []

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