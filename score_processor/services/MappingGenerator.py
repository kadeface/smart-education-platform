"""
映射生成器类 (MappingGenerator)
基于Django模型的映射生成实现
"""
import numpy as np
from typing import Dict, List, Optional
import pandas as pd
import logging
from django.core.cache import cache
from django.db.models import Q
from django.http import HttpResponse
from ..models import StudentMapping, ScoreStudentBasic,BaseSchoolInfo
from django.db import connection, transaction
import openpyxl
from openpyxl.styles import NamedStyle, Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from urllib.parse import quote
class MappingGenerator:
    def __init__(self):
        """初始化映射生成器"""
        self._setup_logging()
        # 基础字段映射（所有学段通用）
        self.base_mapping = {
            '市(区)': 'district_name',
            '学校': 'school_name',
            '姓名': 'student_name',
            '考号': 'exam_number',
            '班级': 'class_name',
            '总分': 'total_score'
        }

        # 可选字段映射
        self.optional_mapping = {
            '学籍号': 'student_id',
            '身份证号': 'id_number'
        }

        # 不同学段的科目映射
        self.subject_mapping = {
            'P': {  # 小学
                '语文': 'chinese',
                '数学': 'math',
                '英语': 'english',
                '科学': 'science'
            },
            'M': {   # 初中
                '语文': 'chinese',
                '数学': 'math',
                '英语': 'english',
                '物理': 'physics',
                '化学': 'chemistry',
                '政治': 'politics',
                '历史': 'history',
                '生物': 'biology',
                '地理': 'geography'
            },
            'H': {   # 高中
                '语文': 'chinese',
                '数学': 'math',
                '英语': 'english',
                '物理': 'physics',
                '化学': 'chemistry',
                '政治': 'politics',
                '历史': 'history',
                '生物': 'biology',
                '地理': 'geography'
            }
        }
    def generate_score_template(self, school_level: str) -> HttpResponse:
        """生成成绩导入模板"""
        try:
            if school_level not in ['P', 'M', 'H']:
                raise ValueError("无效的学段")

            # 创建Excel文件
            wb = openpyxl.Workbook()
            ws = wb.active

            # 获取表头
            headers = []
            # 添加基础字段
            for zh_name, en_name in self.base_mapping.items():
                headers.append(zh_name)

            # 添加学段对应的科目
            for zh_name, en_name in self.subject_mapping[school_level].items():
                headers.append(zh_name)

            # 写入表头
            for col, header in enumerate(headers, 1):
                ws.cell(row=1, column=col, value=header)

            # 设置列宽和样式
            for col in range(1, len(headers) + 1):
                ws.column_dimensions[get_column_letter(col)].width = 15

            # 添加表头样式
            header_style = NamedStyle(name='header_style')
            header_style.font = Font(bold=True)
            header_style.fill = PatternFill(start_color='CCCCCC', end_color='CCCCCC', fill_type='solid')
            header_style.alignment = Alignment(horizontal='center')

            for cell in ws[1]:
                cell.style = header_style

            # 添加示例数据
            example_data = {
                'P': ['某区', '某小学', '张三', '20250001', '三年级1班', '95', '92', '88', '90', '365'],
                'M': ['某区', '某初中', '张三', '20250001', '初一1班',
                      '95', '92', '88', '85', '87', '86', '89', '88', '86', '796'],
                'H': ['某区', '某高中', '张三', '20250001', '高一1班',
                      '95', '92', '88', '85', '87', '86', '89', '88', '86', '796']
            }

            # 写入示例数据
            for col, value in enumerate(example_data[school_level], 1):
                ws.cell(row=2, column=col, value=value)

            # 创建响应
            response = HttpResponse(
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

            # 设置文件名
            level_names = {'P': '小学', 'M': '初中', 'H': '高中'}
            filename = f"{level_names[school_level]}成绩导入模板.xlsx"
            response['Content-Disposition'] = f'attachment; filename="{quote(filename)}"'

            # 保存到响应
            wb.save(response)
            return response

        except Exception as e:
            print(f"生成模板文件失败: {str(e)}")
            raise ValueError(f"生成模板文件失败: {str(e)}")
    def process_data(self, cleaned_data: pd.DataFrame, school_level: str) -> pd.DataFrame:
        """
        处理数据并根据学段映射相应科目

        Args:
            cleaned_data: 待处理的数据框
            school_level: 学段，'primary'表示小学，'secondary'表示初中和高中
        """
        # 处理初中和高中的情况
        if school_level in ['middle', 'high']:
            school_level = 'secondary'

        if school_level not in self.subject_mapping:
            raise ValueError(f"不支持的学段: {school_level}")

        # 合并基础映射和学段特定的科目映射
        current_mapping = self.base_mapping.copy()
        current_mapping.update(self.subject_mapping[school_level])

        # 添加存在的可选字段
        for cn_col, en_col in self.optional_mapping.items():
            if cn_col in cleaned_data.columns:
                current_mapping[cn_col] = en_col

        # 重命名列
        cleaned_data = cleaned_data.rename(columns=current_mapping)
        return cleaned_data


    def _setup_logging(self):
        """配置日志系统"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('mapping_generator.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _get_school_level(self, exam_id: str) -> str:
        """从考试ID解析学段信息

        Args:
            exam_id: 形如 202501-CITY-H-2025 的考试ID

        Returns:
            str: 'P'/'M'/'H' 表示学段
        """
        try:
            # 分割考试ID，获取第三部分的字母
            level_code = exam_id.split('-')[2]

            # 验证学段代码
            if level_code not in ['P', 'M', 'H']:
                raise ValueError(f"无效的学段代码: {level_code}")

            self.logger.info(f"解析到学段代码: {level_code} (考试ID: {exam_id})")
            return level_code

        except Exception as e:
            self.logger.error(f"解析考试ID中的学段信息失败: {str(e)}")
            raise

    def generate(self, cleaned_data: pd.DataFrame, exam_id: str) -> bool:
        """生成映射的主入口方法"""
        try:
            # 从考试ID获取学段信息
            school_level = self._get_school_level(exam_id)
            self.logger.info(f"获取到学段: {school_level}")
            # 获取现有映射（传入学段参数）

            # 清理列名中的空格
            cleaned_data.columns = cleaned_data.columns.str.strip()

            # 打印清理后的列名，用于调试
            self.logger.info(f"清理空格后的DataFrame列名: {cleaned_data.columns.tolist()}")

            # 从考试ID获取学段信息
            school_level = self._get_school_level(exam_id)

            # 获取当前学段的完整映射
            current_mapping = self.base_mapping.copy()
            current_mapping.update(self.subject_mapping[school_level])

            # 添加存在的可选字段
            for cn_col, en_col in self.optional_mapping.items():
                if cn_col in cleaned_data.columns:
                    current_mapping[cn_col] = en_col

            # 检查所需的列是否都存在
            missing_columns = [col for col in self.base_mapping.keys()
                               if col not in cleaned_data.columns]
            if missing_columns:
                raise ValueError(f"缺少必需的列: {missing_columns}")

            # 打印映射前后的列名对应关系
            self.logger.info("映射前后的列名对应关系:")
            for cn_col, en_col in current_mapping.items():
                self.logger.info(f"{cn_col} -> {en_col}")

            with transaction.atomic():
                # 重命名列
                cleaned_data = cleaned_data.rename(columns=current_mapping)

                # 打印重命名后的列名
                self.logger.info(f"重命名后的列名: {cleaned_data.columns.tolist()}")

                # 1. 获取现有映射
                existing_mappings = self._get_existing_mappings(cleaned_data, school_level)

                # 2. 生成新映射
                mapping_results = self._process_mappings(cleaned_data, exam_id, existing_mappings)

                # 3. 更新成绩表
                self._update_score_records(cleaned_data, mapping_results, exam_id)

                return True

        except Exception as e:
            self.logger.error(f"生成映射失败: {str(e)}")
            self.logger.error("错误详情:", exc_info=True)
            return False

    def _get_existing_mappings(self, data: pd.DataFrame, school_level: str) -> Dict:
        try:
            self.logger.info("=== 开始获取现有映射 ===")
            self.logger.info(f"学段: {school_level}")

            # 获取该学段的所有学校
            schools = BaseSchoolInfo.objects.filter(
                school_level=school_level,
                school_name__in=data['school_name'].unique()
            ).values('school_code', 'school_name')

            # 获取学校代码列表
            school_codes = [school['school_code'] for school in schools]
            self.logger.info(f"找到 {len(schools)} 所{school_level}学校")

            # 使用原生SQL查询
            with connection.cursor() as cursor:
                # 构建基础查询
                base_query = """
                    SELECT id, unified_id, student_name, school_name, 
                           exam_number, student_id, id_number, class_name,
                           exam_id, school_level
                    FROM student_mapping
                    WHERE school_level = %s
                """
                base_params = [school_level]

                # 添加区域代码条件
                if school_codes:
                    district_codes = list(set(
                        code[:3] for code in school_codes if code and len(code) >= 3
                    ))
                    district_conditions = " OR ".join(
                        ["SUBSTRING(unified_id, 3, 3) = %s"] * len(district_codes)
                    )
                    base_query += f" AND ({district_conditions})"
                    base_params.extend(district_codes)
                    self.logger.info(f"区域代码条件: {district_codes}")

                # 添加学籍号条件
                if 'student_id' in data.columns:
                    student_ids = data['student_id'].dropna().unique().tolist()
                    if student_ids:
                        id_conditions = " OR ".join(["student_id = %s"] * len(student_ids))
                        base_query += f" AND ({id_conditions})"
                        base_params.extend(student_ids)
                        self.logger.info(f"添加学籍号查询条件，数量: {len(student_ids)}")

                # 添加身份证号条件
                if 'id_number' in data.columns:
                    id_numbers = data['id_number'].dropna().unique().tolist()
                    if id_numbers:
                        id_num_conditions = " OR ".join(["id_number = %s"] * len(id_numbers))
                        base_query += f" AND ({id_num_conditions})"
                        base_params.extend(id_numbers)
                        self.logger.info(f"添加身份证号查询条件，数量: {len(id_numbers)}")

                # 添加考号条件
                if 'exam_number' in data.columns:
                    exam_numbers = data['exam_number'].dropna().unique().tolist()
                    if exam_numbers:
                        exam_conditions = " OR ".join(["exam_number = %s"] * len(exam_numbers))
                        base_query += f" AND ({exam_conditions})"
                        base_params.extend(exam_numbers)
                        self.logger.info(f"添加考号查询条件，数量: {len(exam_numbers)}")

                # 姓名+学校+班级匹配
                if all(col in data.columns for col in ['student_name', 'school_name', 'class_name']):
                    name_school_class = data[['student_name', 'school_name', 'class_name']].dropna()
                    if not name_school_class.empty:
                        # 分批处理
                        batch_size = 500
                        all_results = []

                        for start_idx in range(0, len(name_school_class), batch_size):
                            batch_df = name_school_class.iloc[start_idx:start_idx + batch_size]

                            # 构建批次条件
                            batch_conditions = []
                            batch_params = base_params.copy()  # 复制基础参数

                            for _, row in batch_df.iterrows():
                                batch_conditions.append(
                                    "(student_name = %s AND school_name = %s AND class_name = %s)"
                                )
                                batch_params.extend([
                                    row['student_name'],
                                    row['school_name'],
                                    row['class_name']
                                ])

                            # 构建完整查询
                            batch_query = base_query
                            if batch_conditions:
                                batch_query += f" AND ({' OR '.join(batch_conditions)})"

                            self.logger.info(f"执行批次查询 {start_idx // batch_size + 1}, "
                                             f"条件数: {len(batch_conditions)}")

                            # 执行查询
                            cursor.execute(batch_query, batch_params)

                            # 处理结果
                            columns = [col[0] for col in cursor.description]
                            batch_results = [
                                dict(zip(columns, row))
                                for row in cursor.fetchall()
                            ]

                            self.logger.info(f"本批次找到 {len(batch_results)} 条记录")
                            all_results.extend(batch_results)

                        return all_results

                self.logger.warning("没有找到匹配记录")
                return []

        except Exception as e:
            self.logger.error(f"获取现有映射时出错: {str(e)}")
            self.logger.error("错误详情:", exc_info=True)
            raise

    def _process_mappings(self, data: pd.DataFrame, exam_id: str, existing_mappings: List[Dict]) -> List[Dict]:
        """处理学生映射"""
        try:
            self.logger.info("=== 开始处理映射 ===")

            # 处理同校同名
            data = self._handle_duplicate_names(data, existing_mappings)

            # 将现有映射转换为字典，用于快速查找
            existing_map = {}
            for mapping in existing_mappings:
                key = (
                    mapping['student_name'],
                    mapping['school_name'],
                    mapping['original_student_id']  # 使用original_student_id替代exam_number
                )
                existing_map[key] = mapping

            # 按学校分组处理
            school_groups = data.groupby('school_name')
            new_mappings = []

            for school_name, school_data in school_groups:
                self.logger.info(f"处理学校: {school_name}, 学生数: {len(school_data)}")

                # 该校的新映射列表
                school_new_mappings = []

                # 生成该校所需的统一考号
                new_ids = self._generate_new_id(
                    exam_id=exam_id,
                    school_name=school_name,
                    count=len(school_data)
                )

                # 使用迭代器同时遍历学生数据和统一考号
                for (_, row), unified_id in zip(school_data.iterrows(), new_ids):
                    key = (
                        row['student_name'],
                        row['school_name'],
                        row['exam_number']  # 这里的exam_number就是要存入original_student_id的值
                    )

                    # 检查是否存在映射
                    if key in existing_map:
                        new_mappings.append(existing_map[key])
                        continue

                    # 创建新的映射
                    new_mapping = {
                        'unified_id': unified_id,  # 全局唯一的统一考号
                        'exam_id': exam_id,
                        'original_student_id': row['exam_number'],  # 考试的实际考号
                        'student_name': row['student_name'],
                        'school_name': row['school_name'],
                        'class_name': row['class_name'],
                        'name_tag': row.get('name_tag', ''),
                        'school_level': exam_id.split('-')[2],
                        'is_new': True
                    }

                    # 添加可选字段
                    if 'student_id' in row and pd.notna(row['student_id']):
                        new_mapping['student_id'] = str(row['student_id']).strip()
                    if 'id_number' in row and pd.notna(row['id_number']):
                        new_mapping['id_number'] = str(row['id_number']).strip()

                    school_new_mappings.append(StudentMapping(**new_mapping))
                    new_mappings.append(new_mapping)

                # 批量创建当前学校的记录
                if school_new_mappings:
                    self.logger.info(f"为学校 {school_name} 创建 {len(school_new_mappings)} 条新映射")
                    try:
                        with transaction.atomic():
                            StudentMapping.objects.bulk_create(school_new_mappings)
                    except Exception as e:
                        self.logger.error(f"创建学校 {school_name} 的映射失败: {str(e)}")
                        if school_new_mappings:
                            failed_mapping = school_new_mappings[0].__dict__
                            failed_mapping.pop('_state', None)
                            self.logger.error(f"失败数据示例: {failed_mapping}")
                        raise

            self.logger.info(f"处理完成，总映射数: {len(new_mappings)}")
            return new_mappings

        except Exception as e:
            self.logger.error(f"处理映射时出错: {str(e)}")
            self.logger.error("错误详情:", exc_info=True)
            raise

    def _update_score_records(self, data: pd.DataFrame, mapping_results: List[Dict], exam_id: str):
        """更新成绩记录"""
        try:
            # 获取学段
            school_level = exam_id.split('-')[2]  # H/M/P

            # 将映射结果转换为DataFrame
            mapping_df = pd.DataFrame(mapping_results)

            # 合并数据
            merged_data = pd.merge(
                data,
                mapping_df[['original_student_id', 'unified_id']],
                left_on='exam_number',
                right_on='original_student_id',
                how='left',
                validate='1:1'
            )

            # 检查未匹配记录
            unmatched = merged_data[merged_data['unified_id'].isna()]
            if not unmatched.empty:
                self.logger.error(f"发现 {len(unmatched)} 条未匹配的成绩记录")
                self.logger.error(unmatched[['student_name', 'school_name', 'exam_number']].to_string())
                raise ValueError("存在未匹配的成绩记录")

            # 获取当前学段的科目映射
            current_subjects = self.subject_mapping[school_level]

            # 批量创建成绩记录
            score_records = []

            for _, row in merged_data.iterrows():
                # 设置所有科目成绩默认值为0
                subject_scores = {
                    'chinese': 0, 'math': 0, 'english': 0,
                    'physics': 0, 'chemistry': 0, 'biology': 0,
                    'history': 0, 'politics': 0, 'geography': 0
                }

                # 根据学段更新实际的科目成绩
                for subject_name, field_name in current_subjects.items():
                    if field_name == 'science':
                        # 如果是科学，存入physics字段
                        subject_scores['physics'] = row.get(field_name, 0)
                    else:
                        subject_scores[field_name] = row.get(field_name, 0)

                # 确定分科类型（仅高中需要）
                select_type = self._determine_select_type(row, exam_id) if school_level == 'H' else '未确定'

                # 创建成绩记录
                score_records.append(ScoreStudentBasic(
                    exam_id=exam_id,
                    student_id=row['unified_id'],
                    student_name=row['student_name'],
                    district_name=row['district_name'],
                    school_name=row['school_name'],
                    class_field=row['class_name'],
                    select_type=select_type,
                    **subject_scores,  # 展开所有科目成绩
                    total_score=row.get('total_score', 0)
                ))

            # 使用事务批量创建
            if score_records:
                # 输出分科统计
                select_types = [r.select_type for r in score_records]
                stats = {
                    '理科': select_types.count('理科'),
                    '文科': select_types.count('文科'),
                    '未确定': select_types.count('未确定')
                }
                self.logger.info(f"分科统计: {stats}")

                # 输出科目成绩统计
                subject_stats = {}
                for subject in current_subjects.values():
                    if subject != 'science':  # 跳过science，因为它已经映射到physics
                        count = sum(1 for r in score_records if getattr(r, subject, 0) > 0)
                        if count > 0:
                            subject_stats[subject] = count
                self.logger.info(f"科目成绩统计: {subject_stats}")

                self.logger.info(f"开始创建 {len(score_records)} 条成绩记录")
                with transaction.atomic():
                    ScoreStudentBasic.objects.bulk_create(
                        score_records,
                        batch_size=1000
                    )
                self.logger.info("成绩记录创建完成")

        except Exception as e:
            self.logger.error(f"更新成绩记录时出错: {str(e)}")
            self.logger.error("错误详情:", exc_info=True)
            raise


    def _find_mapping(self, row: pd.Series, mapping_index: Dict) -> Optional[Dict]:
        """按优先级查找映射"""
        # 1. 学籍号匹配
        if row.get('student_id') and row['student_id'] in mapping_index['student_id']:
            return mapping_index['student_id'][row['student_id']]

        # 2. 身份证号匹配
        if row.get('id_number') and row['id_number'] in mapping_index['id_number']:
            return mapping_index['id_number'][row['id_number']]

        # 3. 考号匹配
        if row.get('exam_number') and row['exam_number'] in mapping_index['exam_number']:
            return mapping_index['exam_number'][row['exam_number']]

        # 4. 姓名+学校匹配
        key = (row['student_name'], row['school_name'])
        return mapping_index['name_school'].get(key)

    def _get_school_code(self, school_name_or_code: str) -> str:
        """获取学校代码

        Args:
            school_name_or_code: 学校名称或学校代码

        Returns:
            str: 学校代码
        """
        try:
            # 如果输入的就是学校代码（5位数字），直接返回
            if isinstance(school_name_or_code, str) and len(school_name_or_code) == 5 and school_name_or_code.isdigit():
                return school_name_or_code

            # 从数据库获取学校信息
            school = BaseSchoolInfo.objects.filter(
                Q(school_name=school_name_or_code) | Q(school_code=school_name_or_code)
            ).first()

            if not school:
                error_msg = f"找不到学校信息: {school_name_or_code}"
                self.logger.error(error_msg)
                raise ValueError(error_msg)

            return school.school_code

        except Exception as e:
            error_msg = f"获取学校代码失败: {str(e)}"
            self.logger.error(error_msg)
            self.logger.error("详细错误:", exc_info=True)
            raise ValueError(error_msg)

    def _generate_new_id(self, exam_id: str, school_name: str, count: int = 1) -> List[str]:
        """生成新的统一考号（内部方法）

        Args:
            exam_id: 考试ID (形如 202501-CITY-H-2025)
            school_name: 学校名称
            count: 需要生成的数量

        Returns:
            List[str]: 生成的统一考号列表
        """
        try:
            # 从考试ID获取年份后两位
            grad_year = exam_id.split('-')[-1][-2:]  # 从 2025 获取 25

            # 从基础学校信息表获取学校代码
            school_code = self._get_school_code(school_name)
            prefix = f"{grad_year}{school_code}"

            self.logger.info(f"为学校 {school_name}(代码:{school_code}) 生成 {count} 个新统一考号")
            self.logger.info(f"使用前缀: {prefix} (年份:{grad_year})")

            # 使用缓存优化查询
            cache_key = f"last_unified_id_{prefix}"
            last_id = cache.get(cache_key)

            # 获取起始序号
            if last_id is None:
                # 缓存未命中，查询数据库
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT unified_id 
                        FROM student_mapping 
                        WHERE unified_id LIKE %s 
                        ORDER BY unified_id DESC 
                        LIMIT 1
                        FOR UPDATE
                    """, [f"{prefix}%"])
                    result = cursor.fetchone()

                if result is None:
                    # 没有现有记录，从1开始
                    start_number = 1
                else:
                    # 提取最后4位序号并加1
                    last_id = result[0]  # 从查询结果获取last_id
                    start_number = int(last_id[-4:]) + 1  # 使用start_number保持一致

                # 更新缓存
                if result:  # 只在有结果时更新缓存
                    cache.set(cache_key, last_id, timeout=3600)  # 缓存1小时
            else:
                # 使用缓存的最后ID
                start_number = int(last_id[-4:]) + 1

            # 生成新ID列表
            new_ids = []
            for i in range(count):
                new_number = start_number + i

                # 检查序号是否超出范围
                if new_number > 9999:
                    error_msg = f"学校 {school_name} 的学生编号已超过最大值9999"
                    self.logger.error(error_msg)
                    raise ValueError(error_msg)

                # 生成新ID
                new_id = f"{prefix}{str(new_number).zfill(4)}"
                new_ids.append(new_id)

            # 更新缓存为最后一个ID
            if new_ids:
                cache.set(cache_key, new_ids[-1], timeout=3600)

            # 记录日志
            self.logger.info(f"生成的新统一考号: {new_ids}")
            self.logger.info(f"学校: {school_name}, 毕业年: {grad_year}, "
                             f"学校代码: {school_code}, 数量: {len(new_ids)}")

            return new_ids

        except Exception as e:
            error_msg = f"生成新统一考号失败: {str(e)}"
            self.logger.error(error_msg)
            self.logger.error("详细错误:", exc_info=True)
            raise ValueError(error_msg)


    def _handle_duplicate_names(self, data: pd.DataFrame, existing_mappings: List[Dict]) -> pd.DataFrame:
        """处理同校同名情况

        策略：
        1. 优先使用已有记录的name_tag
        2. 同校同班同名的新生，按顺序生成name_tag
        """
        try:
            self.logger.info("=== 开始处理同校同名 ===")

            # 创建结果DataFrame
            result = data.copy()
            result['name_tag'] = ''

            # 构建现有记录的映射 {(学校, 班级, 姓名): [已用的name_tag列表]}
            existing_tags = {}
            for m in existing_mappings:
                key = (m['school_name'], m['class_name'], m['student_name'])
                if key not in existing_tags:
                    existing_tags[key] = []
                existing_tags[key].append(m['name_tag'])

            # 按学校和班级分组处理
            for (school, class_name), group in data.groupby(['school_name', 'class_name']):
                # 找出该班级的重名学生
                name_counts = group['student_name'].value_counts()
                duplicate_names = name_counts[name_counts > 1].index

                for name in duplicate_names:
                    same_name_rows = group[group['student_name'] == name]
                    key = (school, class_name, name)

                    # 获取已使用的tag列表
                    used_tags = existing_tags.get(key, [])
                    used_numbers = {int(tag) for tag in used_tags if tag.isdigit()}

                    # 为每个同名学生分配tag
                    available_number = 1
                    for row_idx in same_name_rows.index:
                        # 找到未使用的编号
                        while available_number in used_numbers:
                            available_number += 1

                        new_tag = f"{available_number:02d}"
                        result.loc[row_idx, 'name_tag'] = new_tag
                        used_numbers.add(available_number)

                        self.logger.info(
                            f"设置name_tag: {school} {class_name}班 {name} -> {new_tag}"
                        )

            # 记录处理结果
            duplicate_count = len(result[result['name_tag'] != ''])
            if duplicate_count > 0:
                self.logger.info(f"共处理 {duplicate_count} 条同校同班同名记录")
                self.logger.info("处理结果示例:")
                for _, row in result[result['name_tag'] != ''].head().iterrows():
                    self.logger.info(
                        f"学校: {row['school_name']}, "
                        f"班级: {row['class_name']}, "
                        f"姓名: {row['student_name']}, "
                        f"标记: {row['name_tag']}"
                    )
            else:
                self.logger.info("未发现同校同班同名记录")

            return result

        except Exception as e:
            self.logger.error(f"处理同校同名时出错: {str(e)}")
            self.logger.error("错误详情:", exc_info=True)
            raise


    def _get_select_type(self, exam_id: str, grade_name: str = None) -> str:
        """获取分科类型

        Args:
            exam_id: 考试ID，例如: 202501-CITY-H-2025
            grade_name: 年级名称，例如: 高一、高二

        Returns:
            str: 分科类型
                - 'N': 未分科
                - 'S': 理科
                - 'A': 文科
        """
        # 从考试ID获取学段
        school_level = exam_id.split('-')[2]  # H/M/P

        # 如果不是高中，直接返回未分科
        if school_level != 'H':
            return 'N'

        # 如果是高中，需要根据年级判断
        if grade_name:
            grade_name = grade_name.strip()
            if '高一' in grade_name:
                # 判断是否第二学期（可以从考试ID或其他信息判断）
                term = self._get_term_from_exam_id(exam_id)
                return 'N' if term == 1 else ''  # 第一学期未分科，第二学期需要填写
            elif '高二' in grade_name or '高三' in grade_name:
                return ''  # 需要填写分科信息

        # 默认返回未分科
        return 'N'


    def _get_term_from_exam_id(self, exam_id: str) -> int:
        """从考试ID获取学期

        Args:
            exam_id: 考试ID，例如: 202501-CITY-H-2025

        Returns:
            int: 学期（1或2）
        """
        # 示例：从月份判断学期
        month = int(exam_id.split('-')[0][4:6])
        return 1 if month < 6 else 2

    def _determine_select_type(self, row: pd.Series, exam_id: str) -> str:
        """根据成绩确定分科类型

        Args:
            row: 包含成绩信息的数据行
            exam_id: 考试ID

        Returns:
            str: 分科类型 ('文科', '理科', '未确定')
        """
        # 从考试ID获取学段
        school_level = exam_id.split('-')[2]  # H/M/P

        # 如果不是高中，返回未确定
        if school_level != 'H':
            return '未确定'

        # 获取年级和学期信息
        grade_name = row.get('grade_name', '')
        term = self._get_term_from_exam_id(exam_id)

        # 如果是高一上学期，返回未确定
        if '高一' in grade_name and term == 1:
            return '未确定'

        # 如果是需要分科的年级和学期
        if ('高二' in grade_name or '高三' in grade_name) or ('高一' in grade_name and term == 2):
            try:
                # 获取物理和历史成绩，确保转换为数值
                physics_score = float(row.get('physics', 0) or 0)
                history_score = float(row.get('history', 0) or 0)

                # 根据成绩判断文理科
                if physics_score > history_score:
                    return '理科'
                elif history_score > physics_score:
                    return '文科'
                else:
                    # 如果成绩相同，记录警告
                    self.logger.warning(f"""
                    无法判断文理科:
                    学生: {row['student_name']}
                    学校: {row['school_name']}
                    物理成绩: {physics_score}
                    历史成绩: {history_score}
                    """)
                    return '未确定'
            except (ValueError, TypeError) as e:
                self.logger.error(f"成绩转换错误: {row['student_name']} - {str(e)}")
                return '未确定'

        return '未确定'