from ..models import  StudentMapping
import pandas as pd
from django.db import transaction
"""
Student ID Mapping System - 学生统一考号映射系统

功能：生成和管理学生统一考号
作者：瓦块达人
创建日期：2024-03-19

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

    def generate_new_id(self, grad_year, school_code, school_name):
        """生成新的统一考号

        规则：毕业年(2位) + 学校代码(5位) + 序号(4位)
        """
        try:
            # 格式化学校代码
            school_code = str(school_code).zfill(5)
            prefix = f"{grad_year}{school_code}"

            # 查询当前最大序号
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT unified_id 
                        FROM student_mapping 
                        WHERE unified_id LIKE %s 
                        ORDER BY unified_id DESC 
                        LIMIT 1
                    """, [f"{prefix}%"])
                    result = cursor.fetchone()

                if result is None:
                    # 没有现有记录，从1开始
                    new_number = 1
                else:
                    # 提取最后4位序号并加1
                    last_id = result[0]
                    current_number = int(last_id[-4:])
                    new_number = current_number + 1

                if new_number > 9999:
                    raise ValueError(f"学校 {school_name} 的学生编号已超过最大值9999")

                new_id = f"{prefix}{str(new_number).zfill(4)}"
                self.logger.info(f"生成新统一考号: {new_id} (学校: {school_name})")

                return new_id

            except Exception as e:
                self.logger.error(f"查询最大序号失败: {str(e)}")
                raise

        except Exception as e:
            self.logger.error(f"生成新统一考号失败: {str(e)}")
            raise

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

    def process_exam_data(self, file, exam_id):
        """处理考试数据"""
        try:
            print("\n========== 开始处理考试数据 ==========")

            # 读取Excel文件
            df = pd.read_excel(
                file,
                dtype={
                    'student_name': str,
                    'school_name': str,
                    'class_name': str,
                    'original_student_id': str,
                    'student_id': str,
                    'id_number': str
                }
            )
            print(f"成功读取 {len(df)} 条记录")

            with transaction.atomic():
                print("\n---------- 数据验证 ----------")
                df = self.validate_input_data(df)
                print("数据验证完成")

                print("\n---------- 处理重名 ----------")
                df = self.check_duplicates(df)
                print("重名处理完成")

                print("\n---------- 提取考试信息 ----------")
                exam_info = self.extract_exam_info(exam_id)
                print(f"考试信息: {exam_info}")

                # 初始化统计
                stats = {
                    'total': 0, 'new': 0,
                    'student_id_match': 0,
                    'id_number_match': 0,
                    'name_school_match': 0
                }

                # 预先获取所有学校代码
                print("\n---------- 获取学校代码 ----------")
                school_codes = {
                    school: self.school_codes.get(school)
                    for school in df['school_name'].unique()
                }
                for school, code in school_codes.items():
                    print(f"学校: {school}, 代码: {code}")

                # 预先获取每个学校当前的最大序号
                print("\n---------- 初始化学校计数器 ----------")
                school_counters = {}
                for school_name, school_code in school_codes.items():
                    prefix = f"{exam_info['grad_year']}{str(school_code).zfill(5)}"
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            SELECT unified_id 
                            FROM student_mapping 
                            WHERE unified_id LIKE %s 
                            ORDER BY unified_id DESC 
                            LIMIT 1
                        """, [f"{prefix}%"])
                        result = cursor.fetchone()
                        if result:
                            school_counters[school_name] = int(result[0][-4:])
                            print(f"学校: {school_name}")
                            print(f"  最大考号: {result[0]}")
                            print(f"  当前计数: {school_counters[school_name]}")
                        else:
                            school_counters[school_name] = 0
                            print(f"学校: {school_name}")
                            print(f"  无现有考号")
                            print(f"  当前计数: 0")

                # 处理记录
                print("\n---------- 开始处理记录 ----------")
                mapping_records = []

                # 按学校分组处理
                for school_name, school_group in df.groupby('school_name'):
                    print(f"\n=== 处理学校: {school_name} ===")
                    print(f"学生数量: {len(school_group)}")
                    school_code = school_codes.get(school_name)
                    prefix = f"{exam_info['grad_year']}{str(school_code).zfill(5)}"

                    for _, row in school_group.iterrows():
                        unified_id, match_type = self.match_existing_id(row)

                        if unified_id is None:
                            # 使用计数器生成新ID
                            school_counters[school_name] += 1
                            new_number = school_counters[school_name]
                            unified_id = f"{prefix}{str(new_number).zfill(4)}"
                            match_type = 'new'
                            stats['new'] += 1
                            print(f"新考号: {unified_id} -> {row['student_name']}")
                        else:
                            stats[f'{match_type}_match'] += 1
                            print(f"匹配到: {unified_id} -> {row['student_name']}")

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
                        mapping_records.append(mapping)
                        stats['total'] += 1

                    print(f"学校 {school_name} 处理完成，最终计数: {school_counters[school_name]}")

                # 批量保存
                print("\n---------- 开始保存记录 ----------")
                batch_size = 1000
                for i in range(0, len(mapping_records), batch_size):
                    batch = mapping_records[i:i + batch_size]
                    StudentMapping.objects.bulk_create(batch)
                    print(f"保存第 {i // batch_size + 1} 批，{len(batch)} 条记录")

                print("\n========== 处理完成 ==========")
                print(f"总记录数: {stats['total']}")
                print(f"新生成: {stats['new']}")
                print(f"学籍号匹配: {stats['student_id_match']}")
                print(f"身份证号匹配: {stats['id_number_match']}")
                print(f"姓名学校匹配: {stats['name_school_match']}")

                return stats

        except Exception as e:
            print(f"\n========== 处理失败 ==========")
            print(f"错误信息: {str(e)}")
            raise

