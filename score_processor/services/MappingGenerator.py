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
            # 1. 初始化准备
            school_level = self._get_school_level(exam_id)
            self.logger.info(f"=== 开始生成映射 ===")
            self.logger.info(f"学段: {school_level}")

            # 2. 数据清理和列名映射
            cleaned_data = self.process_data(cleaned_data, school_level)
            self.logger.info("完成数据清理和列名映射")

            with transaction.atomic():
                # 3. 获取已有的name_tag
                existing_tags = self._get_existing_name_tags(school_level, exam_id)

                # 4. 处理同校同级重名情况
                cleaned_data = self._handle_duplicate_names(
                    data=cleaned_data,
                    exam_id=exam_id,
                    existing_tags=existing_tags
                )
                self.logger.info("完成同校同级重名处理")

                # 5. 获取现有映射（用于统一考号匹配）
                existing_mappings = self._get_existing_mappings(
                    data=cleaned_data,
                    exam_id=exam_id,
                    school_level=school_level
                )
                self.logger.info(f"获取到 {len(existing_mappings)} 条现有映射")

                # 6. 生成新的映射
                mapping_results = self._process_mappings(
                    data=cleaned_data,
                    exam_id=exam_id,
                    existing_mappings=existing_mappings
                )

                # 7. 更新成绩记录
                self._update_score_records(cleaned_data, mapping_results, exam_id)

                return True

        except Exception as e:
            self.logger.error(f"生成映射失败: {str(e)}")
            self.logger.error("错误详情:", exc_info=True)
            return False

    def _get_existing_name_tags(self, school_level: str, exam_id: str) -> Dict:
        """获取已有的name_tag

        Returns:
            Dict: {(school_name, student_name, grad_year): [已用的name_tag列表]}
        """
        try:
            # 1. 从考试ID获取毕业年份
            grad_year = exam_id.split('-')[-1][-2:]
            self.logger.info(f"获取 {grad_year} 届已有name_tag")

            # 2. 查询已有的name_tag
            query = """
                SELECT 
                    school_name,
                    student_name,
                    name_tag,
                    SUBSTRING(unified_id, 1, 2) as grad_year
                FROM student_mapping
                WHERE school_level = %s
                AND name_tag != ''  -- 只获取有name_tag的记录
            """

            existing_tags = {}
            with connection.cursor() as cursor:
                cursor.execute(query, [school_level])

                for row in cursor.fetchall():
                    school_name, student_name, name_tag, record_grad_year = row
                    key = (school_name, student_name, record_grad_year)

                    if key not in existing_tags:
                        existing_tags[key] = []
                    existing_tags[key].append(name_tag)

            self.logger.info(f"获取到 {len(existing_tags)} 条name_tag记录")
            return existing_tags

        except Exception as e:
            self.logger.error(f"获取已有name_tag时出错: {str(e)}")
            self.logger.error("错误详情:", exc_info=True)
            raise

    def _get_existing_mappings(self, data: pd.DataFrame, exam_id: str, school_level: str) -> Dict:
        """获取已存在的统一考号映射

        Args:
            data: 预处理后的数据
            exam_id: 考试ID
            school_level: 学段代码(H/M/P)

        Returns:
            Dict: 映射字典，包含多种键的映射记录
        """
        try:
            self.logger.info("=== 开始获取现有映射 ===")
            grad_year = exam_id.split('-')[-1][-2:]

            # 基础查询
            base_query = """
                SELECT 
                    unified_id,
                    student_name,
                    school_name,
                    class_name,
                    student_id,
                    id_number,
                    name_tag
                FROM student_mapping
                WHERE school_level = %s
                AND SUBSTRING(unified_id, 1, 2) = %s
            """
            query_params = [school_level, grad_year]

            # 构建查询条件（利用已有索引）
            conditions = []

            # 1. 学籍号匹配 (idx_student_id)
            # 1. 学籍号匹配
            if 'student_id' in data.columns and not data['student_id'].isna().all():
                student_ids = data['student_id'].dropna().unique().tolist()
                if student_ids:
                    conditions.append("student_id IN %s")
                    query_params.append(tuple(student_ids))
                    self.logger.info(f"添加学籍号匹配条件: {len(student_ids)}个")

            # 2. 身份证号匹配
            if 'id_number' in data.columns and not data['id_number'].isna().all():
                id_numbers = data['id_number'].dropna().unique().tolist()
                if id_numbers:
                    conditions.append("id_number IN %s")
                    query_params.append(tuple(id_numbers))
                    self.logger.info(f"添加身份证号匹配条件: {len(id_numbers)}个")

            # 3. 姓名+学校匹配
            if {'student_name', 'school_name'}.issubset(data.columns):
                name_school_pairs = data[['student_name', 'school_name']].drop_duplicates()
                if not name_school_pairs.empty:
                    pairs = [tuple(row) for _, row in name_school_pairs.iterrows()]
                    conditions.append("(student_name, school_name) IN %s")
                    query_params.append(tuple(pairs))
                    self.logger.info(f"添加姓名+学校匹配条件: {len(pairs)}个")

            # 添加条件到查询
            if conditions:
                base_query += " AND (" + " OR ".join(conditions) + ")"

            # 执行查询
            all_results = {}
            with connection.cursor() as cursor:
                self.logger.info(f"执行查询: {base_query}")
                cursor.execute(base_query, query_params)
                columns = [col[0] for col in cursor.description]

                for row in cursor.fetchall():
                    record = dict(zip(columns, row))

                    # 1. 学籍号作为键
                    if record.get('student_id'):
                        all_results[('student_id', record['student_id'])] = record

                    # 2. 身份证号作为键
                    if record.get('id_number'):
                        all_results[('id_number', record['id_number'])] = record

                    # 3. 姓名+学校作为键
                    name_key = (
                        'name_school',
                        record['student_name'],
                        record['school_name']
                    )
                    all_results[name_key] = record

            self.logger.info(f"查询完成:")
            self.logger.info(f"- 总记录数: {len(all_results)}")
            self.logger.info(f"- 学籍号匹配: {len([k for k in all_results if k[0] == 'student_id'])}")
            self.logger.info(f"- 身份证号匹配: {len([k for k in all_results if k[0] == 'id_number'])}")
            self.logger.info(f"- 姓名学校匹配: {len([k for k in all_results if k[0] == 'name_school'])}")

            return all_results

        except Exception as e:
            self.logger.error(f"获取现有映射时出错: {str(e)}")
            self.logger.error("错误详情:", exc_info=True)
            raise

    def _process_mappings(self, data: pd.DataFrame, exam_id: str, existing_mappings: Dict) -> List[Dict]:
        """处理学生映射

        优化策略：
        1. 批量处理匹配
        2. 减少数据库操作
        3. 使用DataFrame操作代替循环
        """
        try:
            self.logger.info("=== 开始处理映射 ===")

            # 1. 创建结果DataFrame
            result_df = data.copy()
            result_df['unified_id'] = None
            result_df['is_new'] = True

            # 2. 批量匹配处理
            # 2.1 学籍号匹配
            if 'student_id' in result_df.columns:
                mask = result_df['student_id'].notna()
                for idx in result_df[mask].index:
                    key = ('student_id', str(result_df.loc[idx, 'student_id']).strip())
                    if key in existing_mappings:
                        result_df.loc[idx, 'unified_id'] = existing_mappings[key]['unified_id']
                        result_df.loc[idx, 'is_new'] = False

            # 2.2 身份证号匹配
            if 'id_number' in result_df.columns:
                mask = (result_df['unified_id'].isna()) & (result_df['id_number'].notna())
                for idx in result_df[mask].index:
                    key = ('id_number', str(result_df.loc[idx, 'id_number']).strip())
                    if key in existing_mappings:
                        result_df.loc[idx, 'unified_id'] = existing_mappings[key]['unified_id']
                        result_df.loc[idx, 'is_new'] = False

            # 2.3 姓名+学校匹配
            mask = result_df['unified_id'].isna()
            for idx in result_df[mask].index:
                key = ('name_school', result_df.loc[idx, 'student_name'], result_df.loc[idx, 'school_name'])
                if key in existing_mappings:
                    result_df.loc[idx, 'unified_id'] = existing_mappings[key]['unified_id']
                    result_df.loc[idx, 'is_new'] = False

            # 3. 为未匹配记录生成新考号
            unmatched_df = result_df[result_df['unified_id'].isna()].copy()
            if not unmatched_df.empty:
                self.logger.info(f"发现 {len(unmatched_df)} 个未匹配学生")

                # 3.1 按学校分组生成新考号
                new_mappings_list = []
                for school_name, school_group in unmatched_df.groupby('school_name'):
                    new_ids = self._generate_new_id(
                        exam_id=exam_id,
                        school_name=school_name,
                        count=len(school_group)
                    )

                    # 更新未匹配记录的unified_id
                    school_indices = school_group.index
                    result_df.loc[school_indices, 'unified_id'] = new_ids

                    # 准备批量创建的数据
                    for idx, unified_id in zip(school_indices, new_ids):
                        row = result_df.loc[idx]
                        new_mappings_list.append({
                            'unified_id': unified_id,
                            'exam_id': exam_id,
                            'original_student_id': row['exam_number'],
                            'student_name': row['student_name'],
                            'school_name': row['school_name'],
                            'class_name': row['class_name'],
                            'school_level': exam_id.split('-')[2],
                            'student_id': str(row['student_id']).strip() if pd.notna(row.get('student_id')) else None,
                            'id_number': str(row['id_number']).strip() if pd.notna(row.get('id_number')) else None,
                            'is_new': True
                        })

                # 3.2 批量创建新记录
                if new_mappings_list:
                    StudentMapping.objects.bulk_create([
                        StudentMapping(**mapping) for mapping in new_mappings_list
                    ])

            # 4. 构建最终结果
            final_mappings = []
            for _, row in result_df.iterrows():
                mapping = {
                    'unified_id': row['unified_id'],
                    'exam_id': exam_id,
                    'original_student_id': row['exam_number'],
                    'student_name': row['student_name'],
                    'school_name': row['school_name'],
                    'class_name': row['class_name'],
                    'school_level': exam_id.split('-')[2],
                    'student_id': str(row['student_id']).strip() if pd.notna(row.get('student_id')) else None,
                    'id_number': str(row['id_number']).strip() if pd.notna(row.get('id_number')) else None,
                    'is_new': row['is_new']
                }
                final_mappings.append(mapping)

            # 5. 记录处理结果
            self.logger.info(f"处理完成:")
            self.logger.info(f"- 总记录数: {len(final_mappings)}")
            self.logger.info(f"- 匹配记录: {len(result_df[~result_df['is_new']])}")
            self.logger.info(f"- 新建记录: {len(result_df[result_df['is_new']])}")

            return final_mappings

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
                how='left'
            )

            # 批量创建成绩记录
            score_records = []
            for _, row in merged_data.iterrows():
                # 设置科目成绩
                subject_scores = {
                    'chinese': row.get('chinese', 0),
                    'math': row.get('math', 0),
                    'english': row.get('english', 0),
                    'physics': row.get('physics', 0),
                    'chemistry': row.get('chemistry', 0),
                    'biology': row.get('biology', 0),
                    'history': row.get('history', 0),
                    'politics': row.get('politics', 0),
                    'geography': row.get('geography', 0)
                }

                # 在这里调用分科判断
                select_type = self._determine_select_type(row, exam_id)

                # 创建成绩记录
                score_records.append(ScoreStudentBasic(
                    exam_id=exam_id,
                    student_id=row['unified_id'],
                    student_name=row['student_name'],
                    district_name=row['district_name'],
                    school_name=row['school_name'],
                    class_field=row['class_name'],
                    select_type=select_type,  # 这里使用判断结果
                    **subject_scores,
                    total_score=row.get('total_score', 0)
                ))

            # 输出分科统计
            if score_records:
                select_types = [r.select_type for r in score_records]
                stats = {
                    '理科': select_types.count('理科'),
                    '文科': select_types.count('文科'),
                    '未确定': select_types.count('未确定')
                }
                self.logger.info(f"分科统计: {stats}")

            # 批量创建记录
            if score_records:
                self.logger.info(f"开始创建 {len(score_records)} 条成绩记录")
                with transaction.atomic():
                    ScoreStudentBasic.objects.bulk_create(score_records, batch_size=1000)
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

    def _handle_duplicate_names(self, data: pd.DataFrame, exam_id: str, existing_tags: Dict) -> pd.DataFrame:
        """处理同校同级重名情况"""
        try:
            self.logger.info("=== 开始处理同校同级重名 ===")

            # 1. 从考试ID获取毕业年份
            grad_year = exam_id.split('-')[-1][-2:]  # 例如：2025 -> 25
            self.logger.info(f"处理 {grad_year} 届学生")

            result = data.copy()
            result['name_tag'] = ''

            # 2. 按学校和毕业年份分组处理
            for school, school_group in data.groupby('school_name'):
                # 找出该校该届的重名学生
                name_counts = school_group['student_name'].value_counts()
                duplicate_names = name_counts[name_counts > 1].index

                if len(duplicate_names) > 0:
                    self.logger.info(f"{school} {grad_year}届 发现 {len(duplicate_names)} 个重名")

                for name in duplicate_names:
                    key = (school, name, grad_year)
                    same_name_rows = school_group[school_group['student_name'] == name]

                    # 获取已使用的tag
                    used_tags = existing_tags.get(key, [])
                    used_numbers = {int(tag) for tag in used_tags if tag.isdigit()}

                    # 为每个同名学生分配新tag
                    available_number = 1
                    for row_idx in same_name_rows.index:
                        while available_number in used_numbers:
                            available_number += 1
                        new_tag = f"{available_number:02d}"
                        result.loc[row_idx, 'name_tag'] = new_tag
                        used_numbers.add(available_number)

                        self.logger.info(
                            f"设置name_tag: {school} {grad_year}届 {name} -> {new_tag} "
                            f"(班级: {result.loc[row_idx, 'class_name']})"
                        )

            # 3. 记录处理结果
            duplicate_count = len(result[result['name_tag'] != ''])
            if duplicate_count > 0:
                self.logger.info(f"共处理 {duplicate_count} 条同校同级重名记录")
                self.logger.info("处理结果示例:")
                for _, row in result[result['name_tag'] != ''].head().iterrows():
                    self.logger.info(
                        f"学校: {row['school_name']}, "
                        f"毕业年份: {grad_year}, "
                        f"姓名: {row['student_name']}, "
                        f"班级: {row['class_name']}, "
                        f"标记: {row['name_tag']}"
                    )
            else:
                self.logger.info("未发现同校同级重名记录")

            return result

        except Exception as e:
            self.logger.error(f"处理同校同级重名时出错: {str(e)}")
            self.logger.error("错误详情:", exc_info=True)
            raise

    def _adjust_name_tags(self, data: pd.DataFrame, school_level: str) -> pd.DataFrame:
        """根据已有的name_tag调整上传数据的标记"""
        try:
            self.logger.info("=== 开始调整name_tag ===")

            # 1. 获取现有的name_tag
            existing_tags = self._get_existing_name_tags(school_level)

            # 2. 调整每个临时标记
            result = data.copy()
            for (school, class_name), group in data.groupby(['school_name', 'class_name']):
                for name in group['student_name'].unique():
                    key = (school, class_name, name)
                    used_tags = existing_tags.get(key, [])
                    used_numbers = {int(tag) for tag in used_tags if tag.isdigit()}

                    # 获取该学生的所有行
                    student_rows = group[group['student_name'] == name]
                    if len(student_rows) > 1:  # 只处理有临时标记的同名学生
                        available_number = 1
                        for row_idx in student_rows.index:
                            while available_number in used_numbers:
                                available_number += 1
                            new_tag = f"{available_number:02d}"
                            result.loc[row_idx, 'name_tag'] = new_tag
                            used_numbers.add(available_number)

            return result

        except Exception as e:
            self.logger.error(f"调整name_tag时出错: {str(e)}")
            raise

    def _get_existing_name_tags(self, school_level: str, exam_id: str) -> Dict:
        """获取已有的name_tag

        Returns:
            Dict: {(school_name, student_name): [已用的name_tag列表]}
        """
        try:
            # 1. 从考试ID获取毕业年份
            grad_year = exam_id.split('-')[-1][-2:]
            self.logger.info(f"获取 {grad_year} 届已有name_tag")

            # 2. 查询已有的name_tag
            query = """
                SELECT 
                    school_name,
                    student_name,
                    name_tag
                FROM student_mapping
                WHERE school_level = %s
                AND SUBSTRING(unified_id, 1, 2) = %s  -- 筛选同一届的学生
                AND name_tag != ''  -- 只获取有name_tag的记录
            """

            existing_tags = {}
            with connection.cursor() as cursor:
                cursor.execute(query, [school_level, grad_year])

                for row in cursor.fetchall():
                    school_name, student_name, name_tag = row
                    key = (school_name, student_name)

                    if key not in existing_tags:
                        existing_tags[key] = []
                    existing_tags[key].append(name_tag)

            self.logger.info(f"获取到 {len(existing_tags)} 个学校的name_tag记录")
            return existing_tags

        except Exception as e:
            self.logger.error(f"获取已有name_tag时出错: {str(e)}")
            self.logger.error("错误详情:", exc_info=True)
            raise

    def _determine_select_type(self, row: pd.Series, exam_id: str) -> str:
        """确定分科类型

        规则：
        1. 8月前按当年计算年级，8月后按下一年计算
        2. 高一下学期开始分科（3月开始）
        3. 有物理成绩就是理科，有历史成绩就是文科
        """
        try:
            # 1. 获取学段，非高中直接返回未确定
            school_level = exam_id.split('-')[2]
            if school_level != 'H':
                return '未确定'

            # 2. 从考试ID获取信息
            exam_date = exam_id[:6]  # 202401
            grad_year = int(exam_id[-4:])  # 2025

            exam_year = int(exam_date[:4])
            exam_month = int(exam_date[4:6])

            # 3. 计算年级：8月前用当年，8月后用下一年
            school_year = exam_year if exam_month < 8 else exam_year + 1
            grade = grad_year - school_year  # 3:高三 2:高二 1:高一

            # 4. 如果是高一且在3月前，不分科
            if grade == 1 and exam_month < 3:
                return '未确定'

            # 5. 根据成绩判断文理科
            physics_score = row.get('physics', 0)
            history_score = row.get('history', 0)

            if pd.notna(physics_score) and physics_score > 0:
                return '理科'
            elif pd.notna(history_score) and history_score > 0:
                return '文科'

            return '未确定'

        except Exception as e:
            self.logger.error(
                f"分科判断出错: {str(e)}, "
                f"exam_id: {exam_id}, "
                f"exam_date: {exam_date}, "
                f"grad_year: {grad_year}, "
                f"grade: {grade}"
            )
            return '未确定'