from ..models import  StudentMapping
import pandas as pd
from django.db import transaction
"""
Student ID Mapping System - 学生统一考号映射系统

功能：生成和管理学生统一考号
作者：瓦块达人
创建日期：2024-10-19

数据库表：student_mapping
统一考号规则：毕业年(2位) + 学校代码(5位) + 序号(4位)
"""
import tkinter as tk
from tkinter import filedialog
import os


from django.db import connection

import logging


class StudentIDMapper:
    def __init__(self):
        self.setup_logger()
        self.load_school_codes()

    def setup_logger(self):
        self.logger = logging.getLogger('student_mapper')

    def load_school_codes(self):
        """从数据库加载学校代码"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT school_name, school_code FROM base_school_info")
                self.school_codes = dict(cursor.fetchall())
            self.logger.info(f"成功加载 {len(self.school_codes)} 个学校代码")
        except Exception as e:
            self.logger.error(f"加载学校代码失败: {str(e)}")
            self.school_codes = {}

    def validate_input_data(self, df):
        """验证输入数据的完整性和格式

        Args:
            df: 输入的DataFrame

        Returns:
            验证后的DataFrame
        """
        try:
            # 1. 检查必需字段
            required_fields = ['student_name', 'school_name', 'class_name', 'original_student_id']
            missing_fields = [field for field in required_fields if field not in df.columns]
            if missing_fields:
                raise ValueError(f"缺少必需字段: {', '.join(missing_fields)}")

            # 2. 检查空值
            for field in required_fields:
                null_count = df[field].isnull().sum()
                if null_count > 0:
                    raise ValueError(f"字段 {field} 存在 {null_count} 条空值记录")

            # 3. 数据清理
            df = df.fillna('')
            string_fields = [
                'student_name',
                'school_name',
                'class_name',
                'original_student_id',
                'student_id',
                'id_number'
            ]

            for field in string_fields:
                if field in df.columns:
                    df[field] = df[field].astype(str).str.strip()

            # 4. 检查学校代码
            unknown_schools = set(df['school_name']) - set(self.school_codes.keys())
            if unknown_schools:
                raise ValueError(f"以下学校未找到对应代码: {', '.join(unknown_schools)}")

            self.logger.info("数据验证完成")
            return df

        except Exception as e:
            self.logger.error(f"数据验证失败: {str(e)}")
            raise


    def check_duplicates(self, df):
        """检查和处理重名情况

        检查顺序：
        1. 同校同班重名（报错）
        2. 同校不同班重名（添加班级标识）

        Args:
            df: 输入的DataFrame

        Returns:
            处理后的DataFrame
        """
        try:
            self.logger.info("开始检查重名情况...")

            # 1. 检查同校同班重名
            class_duplicates = df.groupby(['school_name', 'class_name', 'student_name']).size()
            class_duplicates = class_duplicates[class_duplicates > 1]

            if not class_duplicates.empty:
                error_msg = "发现同校同班重名:\n"
                for (school, class_name, student), count in class_duplicates.items():
                    error_msg += f"学校: {school}, 班级: {class_name}, 姓名: {student}, 数量: {count}\n"
                raise ValueError(error_msg)

            # 2. 检查同校不同班重名
            school_duplicates = df.groupby(['school_name', 'student_name']).size()
            school_duplicates = school_duplicates[school_duplicates > 1]

            if not school_duplicates.empty:
                self.logger.warning("发现同校不同班重名，将添加班级标识")
                df_modified = df.copy()

                for (school, student) in school_duplicates.index:
                    mask = (df_modified['school_name'] == school) & (df_modified['student_name'] == student)
                    same_name_students = df_modified[mask]

                    if len(same_name_students) > 1:
                        self.logger.info(f"\n处理重名: {school} - {student}")
                        for _, row in same_name_students.iterrows():
                            self.logger.info(f"班级: {row['class_name']}")

                        # 添加班级标识
                        df_modified.loc[mask, 'student_name'] = df_modified[mask].apply(
                            lambda x: f"{x['student_name']}({x['class_name']})", axis=1
                        )

                return df_modified

            self.logger.info("未发现重名情况")
            return df

        except Exception as e:
            self.logger.error(f"重名检查失败: {str(e)}")
            raise


    def match_existing_id(self, row):
        """按优先级匹配已有统一考号

        匹配优先级：
        1. 学籍号
        2. 身份证号
        3. 姓名+学校

        Args:
            row: 学生记录行

        Returns:
            (unified_id, match_type) 或 (None, None)
        """
        try:
            # 1. 通过学籍号匹配
            if row.get('student_id'):
                mapping = StudentMapping.objects.filter(
                    student_id=row['student_id']
                ).order_by('-create_time').first()
                if mapping:
                    return mapping.unified_id, 'student_id'

            # 2. 通过身份证号匹配
            if row.get('id_number'):
                mapping = StudentMapping.objects.filter(
                    id_number=row['id_number']
                ).order_by('-create_time').first()
                if mapping:
                    return mapping.unified_id, 'id_number'

            # 3. 通过姓名+学校匹配
            mapping = StudentMapping.objects.filter(
                student_name=row['student_name'],
                school_name=row['school_name']
            ).order_by('-create_time').first()
            if mapping:
                return mapping.unified_id, 'name_school'

            return None, None

        except Exception as e:
            self.logger.error(f"匹配已有统一考号失败: {str(e)}")
            return None, None

    def save_mapping(self, records):
        """保存映射记录到数据库

        Args:
            records: StudentMapping对象列表
        """
        try:
            # 使用Django的批量创建
            StudentMapping.objects.bulk_create(records)

            self.logger.info(f"成功保存 {len(records)} 条映射记录")

            # 生成统计信息
            stats = {
                'total': len(records),
                'new': sum(1 for r in records if r.is_new),
                'student_id_match': sum(1 for r in records if r.match_type == 'student_id'),
                'id_number_match': sum(1 for r in records if r.match_type == 'id_number'),
                'name_school_match': sum(1 for r in records if r.match_type == 'name_school')
            }

            self.logger.info("\n保存统计:")
            self.logger.info(f"总记录数: {stats['total']}")
            self.logger.info(f"新生成统一考号: {stats['new']}")
            self.logger.info(f"学籍号匹配: {stats['student_id_match']}")
            self.logger.info(f"身份证号匹配: {stats['id_number_match']}")
            self.logger.info(f"姓名学校匹配: {stats['name_school_match']}")

            return stats

        except Exception as e:
            self.logger.error(f"保存映射记录失败: {str(e)}")
            raise

    def extract_exam_info(self, exam_id):
        """从考试ID提取信息

        考试ID格式：年月-类型-学段-毕业年
        例如：202408-DIST-H-2025

        Args:
            exam_id: 考试ID

        Returns:
            dict: 包含grad_year和school_level的字典
        """
        try:
            parts = exam_id.split('-')
            if len(parts) != 4:
                raise ValueError(f"考试ID格式错误: {exam_id}")

            grad_year = parts[3][-2:]  # 取毕业年份的后两位
            school_level = parts[2]  # 获取学段标识

            return {
                'grad_year': grad_year,
                'school_level': school_level
            }

        except Exception as e:
            self.logger.error(f"解析考试ID失败: {str(e)}")
            raise

    def preload_existing_mappings(self, student_data_list):
        """预加载所有可能的映射关系"""
        # 1. 收集所有唯一标识
        student_ids = {s['student_id'] for s in student_data_list if s.get('student_id')}
        id_numbers = {s['id_number'] for s in student_data_list if s.get('id_number')}
        name_school_pairs = {
            (s['student_name'], s['school_name'])
            for s in student_data_list
        }

        # 2. 批量查询并保存到内存
        self.student_id_mappings = {
            mapping.student_id: mapping.unified_id
            for mapping in StudentMapping.objects.filter(student_id__in=student_ids)
        }

        self.id_number_mappings = {
            mapping.id_number: mapping.unified_id
            for mapping in StudentMapping.objects.filter(id_number__in=id_numbers)
        }

        self.name_school_mappings = {
            (mapping.student_name, mapping.school_name): mapping.unified_id
            for mapping in StudentMapping.objects.filter(
                student_name__in=[pair[0] for pair in name_school_pairs],
                school_name__in=[pair[1] for pair in name_school_pairs]
            )
        }

        print(f"预加载映射记录:")
        print(f"- 学籍号匹配: {len(self.student_id_mappings)}")
        print(f"- 身份证号匹配: {len(self.id_number_mappings)}")
        print(f"- 姓名学校匹配: {len(self.name_school_mappings)}")

    def match_existing_id(self, student_data):
        """按优先级匹配现有统一考号"""
        # 1. 通过学籍号匹配
        if student_data.get('student_id'):
            unified_id = self.student_id_mappings.get(student_data['student_id'])
            if unified_id:
                return unified_id, 'student_id'

        # 2. 通过身份证号匹配
        if student_data.get('id_number'):
            unified_id = self.id_number_mappings.get(student_data['id_number'])
            if unified_id:
                return unified_id, 'id_number'

        # 3. 通过姓名+学校匹配
        name_school_key = (student_data['student_name'], student_data['school_name'])
        unified_id = self.name_school_mappings.get(name_school_key)
        if unified_id:
            return unified_id, 'name_school'

        # 4. 如果都没找到，返回 None
        return None, None

    def process_exam_data(self, data, exam_id):
        """处理考试数据生成统一考号"""
        try:
            print("\n========== 开始生成统一考号 ==========")

            # 1. 预加载所有现有映射
            self.preload_existing_mappings(data)

            # 2. 初始化统计和学校计数器
            stats = {'total': 0, 'new': 0, 'student_id_match': 0,
                     'id_number_match': 0, 'name_school_match': 0}

            exam_info = self.extract_exam_info(exam_id)
            school_counters = self._initialize_school_counters(data, exam_info)

            # 3. 处理每条记录
            mapping_records = []
            for student in data:
                # 尝试匹配现有考号
                unified_id, match_type = self.match_existing_id(student)

                if unified_id is None:
                    # 生成新考号
                    school_name = student['school_name']
                    school_code = self.school_codes[school_name]
                    school_counters[school_name] += 1

                    unified_id = f"{exam_info['grad_year']}{str(school_code).zfill(5)}{str(school_counters[school_name]).zfill(4)}"
                    match_type = 'new'
                    stats['new'] += 1
                    print(f"新考号: {unified_id} -> {student['student_name']}")
                else:
                    # 使用匹配到的考号
                    stats[f'{match_type}_match'] += 1
                    print(f"匹配到: {unified_id} -> {student['student_name']}")

                # 创建映射记录
                mapping = StudentMapping(
                    unified_id=unified_id,
                    exam_id=exam_id,
                    original_student_id=student['original_student_id'],
                    student_id=student.get('student_id'),
                    id_number=student.get('id_number'),
                    student_name=student['student_name'],
                    school_name=student['school_name'],
                    class_name=student['class_name'],
                    school_level=exam_info['school_level'],
                    match_type=match_type,
                    is_new=(match_type == 'new')
                )
                mapping_records.append(mapping)
                stats['total'] += 1

            # 4. 批量保存
            self._batch_save_mappings(mapping_records)

            print("\n========== 处理完成 ==========")
            self._print_stats(stats)
            return stats

        except Exception as e:
            print(f"\n========== 处理失败 ==========")
            print(f"错误信息: {str(e)}")
            raise

    def _initialize_school_counters(self, school_codes, grad_year):
        """初始化学校计数器"""
        school_counters = {}
        for school_name, school_code in school_codes.items():
            prefix = f"{grad_year}{str(school_code).zfill(5)}"
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT unified_id 
                    FROM student_mapping 
                    WHERE unified_id LIKE %s 
                    ORDER BY unified_id DESC 
                    LIMIT 1
                """, [f"{prefix}%"])
                result = cursor.fetchone()
                school_counters[school_name] = int(result[0][-4:]) if result else 0
                print(f"学校: {school_name}, 当前计数: {school_counters[school_name]}")
        return school_counters

    def _process_school_group(self, school_group, school_name, school_codes,
                              school_counters, exam_info, exam_id, stats):
        """处理单个学校的学生组"""
        mappings = []
        school_code = school_codes.get(school_name)
        prefix = f"{exam_info['grad_year']}{str(school_code).zfill(5)}"

        for _, row in school_group.iterrows():
            unified_id, match_type = self.match_existing_id(row)

            if unified_id is None:
                school_counters[school_name] += 1
                unified_id = f"{prefix}{str(school_counters[school_name]).zfill(4)}"
                match_type = 'new'
                stats['new'] += 1
            else:
                stats[f'{match_type}_match'] += 1

            mapping = StudentMapping(
                unified_id=unified_id,
                exam_id=exam_id,
                original_student_id=row['original_student_id'],
                student_id=row.get('student_id'),
                id_number=row.get('id_number'),
                student_name=row['student_name'],
                school_name=row['school_name'],
                class_name=row['class_name'],
                school_level=exam_info['school_level'],
                match_type=match_type,
                is_new=(match_type == 'new')
            )
            mappings.append(mapping)
            stats['total'] += 1

        return mappings

    def _batch_save_mappings(self, mapping_records, batch_size=1000):
        """批量保存映射记录"""
        for i in range(0, len(mapping_records), batch_size):
            batch = mapping_records[i:i + batch_size]
            StudentMapping.objects.bulk_create(batch)
            print(f"保存第 {i // batch_size + 1} 批，{len(batch)} 条记录")

    def _print_stats(self, stats):
        """打印统计信息"""
        print(f"总记录数: {stats['total']}")
        print(f"新生成: {stats['new']}")
        print(f"学籍号匹配: {stats['student_id_match']}")
        print(f"身份证号匹配: {stats['id_number_match']}")
        print(f"姓名学校匹配: {stats['name_school_match']}")

