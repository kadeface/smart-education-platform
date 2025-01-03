"""
Student ID Mapper - 学生ID映射生成程序

功能说明：
此程序用于生成学生统一考号。将原有的不统一学生ID映射为统一格式的考号。

考号规则：
- 11位数字组成：毕业年(2位) + 学校编码(5位) + 序号(4位)
- 例如：2400001001，表示24年毕业、00001学校、第0001号学生

数据库依赖：
- 数据库名：score_analysis
- 依赖表：
  - base_school_info：学校基础信息表
  - student_mapping：学生ID映射表

输入文件要求(students.xlsx)：
- unified_student_id：原有学生ID
- student_name：学生姓名
- school_name：学校名称
- class_name：班级名称
可选项：
-student_id：学籍号
-id_number：身份证号


输出文件说明(mapping_results_考试ID_时间戳.xlsx)：
- exam_id：考试ID
- exam_student_id：生成的统一考号
- unified_student_id：原有学生ID
- student_name：学生姓名
- school_name：学校名称
- class_name：班级名称
- student_id：学籍号
- id_number：身份证号
- match_type：匹配类型（新建映射/已有映射）
- confidence：匹配置信度
- create_time：创建时间

使用示例：
db_config = {
    'host': 'localhost',
    'user': 'your_username',
    'password': 'your_password',
    'database': 'score_analysis'
}
mapper = StudentIDMapper(db_config)
result_df = mapper.process_new_exam(
    excel_path='students.xlsx',
    exam_id='202401',
    grad_year='24'
)
设计者：瓦块达人
辅助者：Claude
创建日期：2024-11-18
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from datetime import datetime


class StudentIDMapper:
    def __init__(self, db_config):
        """初始化数据库连接
        Args:
            db_config: 数据库配置字典，包含host, user, password, database
        """
        self.db_config = db_config
        self.engine = create_engine(
            f"mysql+pymysql://{db_config['user']}:{db_config['password']}@"
            f"{db_config['host']}/{db_config['database']}?charset=utf8mb4"
        )
        self.current_max_ids = {}  # 用于存储当前批次各学校的最大考号
        # 加载学校编码映射
        self.load_school_codes()

    def load_school_codes(self):
        """从base_school_info表加载学校编码"""
        try:
            query = """
            SELECT school_name, school_code as school_code
            FROM base_school_info
            """
            self.school_codes = pd.read_sql(query, self.engine).set_index('school_name')['school_code'].to_dict()
            print(f"成功加载 {len(self.school_codes)} 个学校编码")
        except Exception as e:
            print(f"加载学校编码时出错: {str(e)}")
            self.school_codes = {}

    def get_school_code(self, school_name):
        """根据学校名称获取学校编码"""
        return self.school_codes.get(school_name)

    def generate_exam_student_id(self, grad_year, school_code):
        """生成统一考号"""
        try:
            school_code = str(school_code).zfill(5)
            prefix = f"{grad_year}{school_code}"

            # 检查当前批次是否已有该学校的考号
            if prefix not in self.current_max_ids:
                # 从数据库查询该学校最大考号
                query = """
                   SELECT exam_student_id as max_id
                   FROM student_mapping 
                   WHERE exam_student_id LIKE %s
                   ORDER BY exam_student_id DESC
                   LIMIT 1
                   """
                search_pattern = f"{prefix}%"
                result = pd.read_sql(query, self.engine, params=(search_pattern,))

                if result.empty or pd.isna(result['max_id'].iloc[0]):
                    self.current_max_ids[prefix] = f"{prefix}0000"  # 初始值
                else:
                    self.current_max_ids[prefix] = result['max_id'].iloc[0]

            # 获取当前最大值并加1
            current_num = int(self.current_max_ids[prefix][-4:])
            new_num = str(current_num + 1).zfill(4)
            new_id = f"{prefix}{new_num}"

            # 更新当前批次的最大值
            self.current_max_ids[prefix] = new_id

            print(f"生成新ID: {new_id}")
            return new_id

        except Exception as e:
            print(f"生成考号时出错: {str(e)}")
            return None

    def check_and_modify_duplicate_names(self, excel_path):
        """
        检查并处理同校不同班同名学生
        Args:
            excel_path: Excel文件路径
        Returns:
            修改后的DataFrame, 是否有修改(Boolean)
        """
        try:
            # 读取Excel文件
            df = pd.read_excel(excel_path)
            print(f"成功读取 {len(df)} 条学生记录")

            # 检查同校不同班同名
            df_group = df.groupby(['school_name', 'student_name']).agg({
                'class_name': lambda x: len(set(x))  # 统计不同班级的数量
            }).reset_index()

            # 找出同校不同班的同名学生
            duplicates = df_group[df_group['class_name'] > 1]

            if not duplicates.empty:
                print("\n发现同校不同班同名学生:")
                df_modified = df.copy()  # 创建副本进行修改
                modified_count=0 #增加计数器
                for _, row in duplicates.iterrows():
                    # 找到同校同名的学生
                    same_students_mask = (
                            (df_modified['school_name'] == row['school_name']) &
                            (df_modified['student_name'] == row['student_name'])
                    )
                    same_students = df_modified[same_students_mask]
                    print(f"\n学校: {row['school_name']}")
                    print(f"姓名: {row['student_name']}")
                    print("原始记录:")
                    print(same_students[['school_name', 'class_name', 'student_name', 'unified_student_id']])

                    # 修改第二条及以后记录的名字
                    for i, (idx, _) in enumerate(same_students.iterrows()):
                        if i > 0:  # 跳过第一条记录
                            df_modified.loc[idx, 'student_name'] = f"{row['student_name']}_{i}"
                            modified_count += 1
                print("\n名字修改后的记录:")
                print(df_modified[['school_name', 'class_name', 'student_name', 'unified_student_id']])
                print(f"\n总共修改了{modified_count}")
                # 保存修改后的数据
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                modified_file = f'modified_names_{timestamp}.xlsx'
                df_modified.to_excel(modified_file, index=False)
                print(f"\n修改后的数据已保存到: {modified_file}")
                print("请检查修改后的数据是否正确，确认无误后再进行考号生成")

                return True, modified_file

            print("未发现同校不同班同名学生，可以直接进行考号生成")
            return False, excel_path

        except Exception as e:
            print(f"处理同校不同班同名时出错: {str(e)}")
            return False, None
    def check_existing_mapping(self, school_name, student_name):
        """检查是否已有映射
        Args:
            unified_student_id: 原有学生ID
        Returns:
            已存在的exam_student_id或None
        """
        try:
            query = """
               SELECT exam_id, exam_student_id, unified_student_id, 
                      student_name,  school_name, class_name, create_time
               FROM student_mapping 
               WHERE school_name = %s 
               AND student_name = %s
               ORDER BY create_time DESC
               """
            params = (school_name, student_name)
            result = pd.read_sql(query, self.engine, params=params)
            #print(f"查找学生 - 学校: {school_name}, 姓名: {student_name}")
            #print(f"查询结果: {result}")

            if not result.empty:
                return {
                    'exam_student_id': result['exam_student_id'].iloc[0],
                    'unified_student_id': result['unified_student_id'].iloc[0],
                    'student_name': result['student_name'].iloc[0],
                    'school_name': result['school_name'].iloc[0],
                    'class_name': result['class_name'].iloc[0],
                    'last_exam_id': result['exam_id'].iloc[0],
                    'create_time': result['create_time'].iloc[0]
                }

                #班级不匹配，说明是另外一个班的同校同名学生
            return None

        except Exception as e:
            print(f"检查映射时出错: {str(e)}")
            return None

    def process_new_exam(self, excel_path, exam_id, grad_year):
        try:
            # 读取Excel数据
            df = pd.read_excel(
                excel_path,
                dtype={
                    'unified_student_id': str,
                    'student_name': str,
                    'school_name': str,
                    'class_name': str
                }
            )

            print(f"成功读取 {len(df)} 条学生记录")

            # 准备映射数据
            mapping_records = []
            error_records = []

            for idx, row in df.iterrows():
                try:
                    # 通过学校和姓名查找已有考号
                    existing_exam_student_id = self.check_existing_mapping(
                        row['school_name'],
                        row['student_name']
                    )

                    if existing_exam_student_id:
                        # 已有考号，直接使用
                        #print(f"找到已有考号: {row['student_name']} - {existing_exam_id}")
                        exam_student_id = existing_exam_student_id['exam_student_id']
                        match_type = '已有映射'
                    else:
                        # 生成新考号
                        school_code = self.get_school_code(row['school_name'])
                        if school_code is None:
                            error_records.append(f"第 {idx + 2} 行: 未找到学校编码 {row['school_name']}")
                            continue

                        exam_student_id = self.generate_exam_student_id(grad_year, school_code)
                        if exam_student_id is None:
                            error_records.append(f"第 {idx + 2} 行: 生成考号失败")
                            continue

                       # print(f"生成新考号: {row['student_name']} - {exam_student_id}")
                        match_type = '新建映射'

                    # 记录映射
                    mapping_records.append({
                        'exam_id': exam_id,
                        'exam_student_id': exam_student_id,
                        'unified_student_id': row['unified_student_id'],
                         'student_name': row['student_name'],
                        'school_name': row['school_name'],
                        'class_name': row['class_name'],
                        'match_type': match_type,
                        'confidence': 1.0,
                        'create_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })

                except Exception as e:
                    error_records.append(f"第 {idx + 2} 行处理出错: {str(e)}")


            # 输出处理结果
            print(f"\n处理结果:")
            print(f"总记录数: {len(df)}")
            print(f"成功处理: {len(mapping_records)}")
            print(f"错误记录: {len(error_records)}")
            # 合并所有映射记录
            all_mappings = pd.DataFrame(mapping_records)

            # 导出结果
            if not all_mappings.empty:
                output_file = f'mapping_results_{exam_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
                all_mappings.to_excel(output_file, index=False)
                print(f"\n结果已导出到：{output_file}")

            return all_mappings
            if error_records:
                print("\n错误详情:")
                for error in error_records:
                    print(error)

            return pd.DataFrame(mapping_records)

        except Exception as e:
            print(f"处理数据时出错: {str(e)}")
            return pd.DataFrame()

# 使用示例
if __name__ == "__main__":
    # 数据库配置
    db_config = {
        'host': 'localhost',
        'user': 'root',
        'password': 'YYrr181314',
        'database': 'score_analysis'
    }

    try:
        # 创建映射器实例
        mapper = StudentIDMapper(db_config)
        input_file='202408-DIST-H.xlsx'
        exam_id='202408-DIST-H'
        grad_year=25
        # 第一步：处理同校同名y
        # 第一步：处理同校同名
        has_modified, output_file = mapper.check_and_modify_duplicate_names(input_file)

        if has_modified:
            print(f"\n请检查输出文件 {output_file}")
            confirm = input("确认是否继续生成考号？(y/n): ")
            if confirm.lower() == 'y':
                # 使用修改后的文件生成考号
                mapper.process_new_exam(output_file, exam_id, grad_year)
            else:
                print("已取消考号生成")
        elif output_file:
            # 直接使用原文件生成考号
            mapper.process_new_exam(output_file, exam_id, grad_year)
        else:
            print("\n处理过程出错，请检查日志")

    except Exception as e:
        print(f"程序执行出错: {str(e)}")

