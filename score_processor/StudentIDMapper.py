"""
学生统一考号生成系统

功能：
1. 检查同校同班重名情况，发现则报错
2. 处理同校不同班重名情况 - 自动添加数字后缀
3. 生成统一学生编号（年份2位+学校代码5位+学生编号4位）
4. 建立考试号与统一考号的映射

作者：瓦块达人
技术支持：Claude
创建日期：2024-11-20
"""

import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime
import logging


class StudentIDMapper:
    def __init__(self, db_config):
        """初始化数据库连接"""
        self.engine = create_engine(
            f"mysql+pymysql://{db_config['user']}:{db_config['password']}@"
            f"{db_config['host']}/{db_config['database']}?charset=utf8mb4"
        )
        # 设置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('student_mapping.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.load_school_codes()

    def load_school_codes(self):
        """加载学校代码"""
        try:
            query = "SELECT school_name, school_code FROM base_school_info WHERE school_level='高中'"
            self.school_codes = pd.read_sql(query, self.engine).set_index('school_name')['school_code'].to_dict()
            self.logger.info(f"成功加载 {len(self.school_codes)} 个学校代码")
            self.logger.info("\n学校代码：")
            for school, code in self.school_codes.items():
                self.logger.info(f"{school}: {code}")
        except Exception as e:
            self.logger.error(f"加载学校代码出错: {str(e)}")
            self.school_codes = {}

    def check_same_class_duplicates(self, df):
        """
        检查同班重名情况
        返回: (是否有同班重名, 错误信息)
        """
        try:
            # 按学校、班级和姓名分组统计
            class_duplicates = df.groupby(['school_name', 'class_name', 'student_name']).size().reset_index(
                name='count')
            class_duplicates = class_duplicates[class_duplicates['count'] > 1]

            if not class_duplicates.empty:
                error_msg = "发现以下同班重名情况：\n"
                for _, row in class_duplicates.iterrows():
                    error_msg += f"\n学校：{row['school_name']}"
                    error_msg += f"\n班级：{row['class_name']}"
                    error_msg += f"\n姓名：{row['student_name']}"
                    error_msg += f"\n重复次数：{row['count']}\n"

                    # 获取详细信息
                    mask = (df['school_name'] == row['school_name']) & \
                           (df['class_name'] == row['class_name']) & \
                           (df['student_name'] == row['student_name'])
                    duplicates = df[mask]

                    error_msg += "\n详细记录：\n"
                    for _, dup in duplicates.iterrows():
                        error_msg += f"考号：{dup['student_id']}\n"

                error_msg += "\n请人工核实后重新导入数据。"
                return True, error_msg

            return False, ""

        except Exception as e:
            error_msg = f"检查同班重名时出错: {str(e)}"
            self.logger.error(error_msg)
            return True, error_msg


    def check_duplicates(self, df):
        """
        检查和处理重名情况:
        1. 同校同名都加班级号后缀
        2. 如果加了班级号后还有重名（同校同班），则再加数字编号
        """
        try:
            # 确保class_name列为字符串类型
            df['class_name'] = df['class_name'].astype(str)

            # 添加班级号列（提取班级名称的后两位数字）
            df['class_num'] = df['class_name'].str.extract(r'(\d{2})$', expand=False)

            # 检查是否存在无法提取班级号的记录
            invalid_mask = df['class_num'].isnull()
            if invalid_mask.any():
                self.logger.error("存在无法提取班级号的记录:")
                invalid_records = df[invalid_mask]
                self.logger.error(invalid_records[['school_name', 'class_name', 'student_name']].to_string())
                raise ValueError("部分班级名称格式不正确，无法提取班级号")

            # 1. 先处理同校同名情况：添加班级号后缀
            school_dupes = df.groupby(['school_name', 'student_name']).size().reset_index(name='count')
            school_dupes = school_dupes[school_dupes['count'] > 1]

            if not school_dupes.empty:
                self.logger.info("\n发现同校同名情况：")

                for _, dup in school_dupes.iterrows():
                    school_name = dup['school_name']
                    student_name = dup['student_name']

                    # 获取重名记录
                    mask = (df['school_name'] == school_name) & \
                           (df['student_name'] == student_name)
                    dup_records = df[mask]

                    self.logger.info(f"\n学校：{school_name}")
                    self.logger.info(f"姓名：{student_name}")
                    self.logger.info("原始记录：")
                    for _, row in dup_records.iterrows():
                        self.logger.info(f"班级：{row['class_name']} | 考号：{row['student_id']}")

                    # 给所有记录添加班级号后缀
                    for idx in dup_records.index:
                        class_num = df.loc[idx, 'class_num']
                        new_name = f"{student_name}_{class_num}"
                        df.loc[idx, 'student_name'] = new_name
                        self.logger.info(f"添加班级号：{student_name} -> {new_name}")

            # 2. 检查添加班级号后是否还有重名（同校同名同班级号）
            name_with_class = df.groupby(['school_name', 'student_name']).size().reset_index(name='count')
            name_with_class = name_with_class[name_with_class['count'] > 1]

            if not name_with_class.empty:
                self.logger.info("\n发现同校同班重名情况：")

                for _, dup in name_with_class.iterrows():
                    school_name = dup['school_name']
                    student_name = dup['student_name']  # 此时的student_name已包含班级号后缀

                    # 获取重名记录
                    mask = (df['school_name'] == school_name) & \
                           (df['student_name'] == student_name)
                    dup_records = df[mask].sort_values('student_id')

                    self.logger.info(f"\n学校：{school_name}")
                    self.logger.info(f"姓名：{student_name}")
                    self.logger.info("重名记录：")
                    for _, row in dup_records.iterrows():
                        self.logger.info(f"考号：{row['student_id']}")

                    # 所有记录都添加数字编号，从0开始
                    for i, idx in enumerate(dup_records.index):
                        new_name = f"{student_name}_{i}"
                        df.loc[idx, 'student_name'] = new_name
                        self.logger.info(f"添加编号：{student_name} -> {new_name}")

            # 删除临时的班级号列
            df = df.drop('class_num', axis=1)
            return df

        except Exception as e:
            self.logger.error(f"处理重名情况时出错: {str(e)}")
            self.logger.error("出错的数据类型:")
            for col in ['school_name', 'class_name', 'student_name']:
                self.logger.error(f"{col} 类型: {df[col].dtype}")
            raise

    def get_school_max_numbers(self, existing_mappings):
        """
        从existing_mappings中获取各学校的最大编号
        参数:
        existing_mappings: 现有的映射字典，key为school_name_class_name_student_name，value为unified_id
        返回: dict, key为学校名称，value为当前最大编号
        """
        try:
            result = {}

            # 检查是否有映射记录
            if not existing_mappings:
                self.logger.info("没有现有映射记录，所有学校从0001开始编号")
                return {}

            # 从映射key中提取所有学校名称
            schools = set()
            for key in existing_mappings.keys():
                school_name = key.split('_')[0]  # 第一部分是学校名
                schools.add(school_name)

            for school_name in schools:
                try:
                    # 获取学校代码
                    school_code = str(self.school_codes.get(school_name, '00000')).zfill(5)
                    self.logger.info("处理学校: {}, 代码: {}".format(school_name, school_code))

                    # 找出该学校的所有记录
                    numbers = []
                    prefix = f"25{school_code}"

                    # 遍历现有映射找出属于该学校的记录
                    for unified_id in existing_mappings.values():
                        if unified_id.startswith(prefix) and len(unified_id) == 11:
                            try:
                                num = int(unified_id[-4:])
                                numbers.append(num)
                            except (ValueError, IndexError):
                                continue

                    if not numbers:
                        max_num = 0
                        self.logger.info("学校 {} 没有历史记录，从0001开始".format(school_name))
                    else:
                        max_num = max(numbers)
                        self.logger.info("学校 {} 当前最大编号: {}，共有记录 {} 条".format(
                            school_name, max_num, len(numbers)))

                    result[school_name] = max_num

                except Exception as e:
                    self.logger.error("处理学校 {} 时出错: {}".format(school_name, str(e)))
                    self.logger.error("使用默认值0")
                    result[school_name] = 0

            return result

        except Exception as e:
            self.logger.error("获取学校最大编号时出错: {}".format(str(e)))
            import traceback
            self.logger.error("错误详细信息:\n{}".format(traceback.format_exc()))
            raise
    def get_existing_mapping(self):
        """
        获取已有的映射记录
        返回一个字典，key为学校名_学生名，value为统一考号
        """
        try:
            query = """
                SELECT DISTINCT school_name, student_name, unified_id 
                FROM student_mapping
            """
            existing_df = pd.read_sql(query, self.engine)

            # 打印当前已有的映射记录，用于调试
            self.logger.info("\n现有映射记录：")
            for _, row in existing_df.iterrows():
                self.logger.info(f"学校：{row['school_name']}, 学生：{row['student_name']}, 统一考号：{row['unified_id']}")

            # 创建查找字典
            mapping_dict = {}
            for _, row in existing_df.iterrows():
                key = f"{row['school_name']}_{row['student_name']}"
                mapping_dict[key] = row['unified_id']

            self.logger.info(f"\n共加载 {len(mapping_dict)} 条已有映射记录")
            return mapping_dict

        except Exception as e:
            self.logger.error(f"获取已有映射记录时出错: {str(e)}")
            return {}
    def process_exam_data(self, excel_path, exam_id):
        try:
            # 1. 读取考试数据
            self.logger.info("开始读取Excel文件: {}".format(excel_path))
            df = pd.read_excel(excel_path)
            self.logger.info("成功读取 {} 条记录".format(len(df)))

            # 2. 处理重名情况
            self.logger.info("开始处理重名情况...")
            df = self.check_duplicates(df)

            # 3. 获取已有的映射记录
            self.logger.info("开始获取已有映射记录...")
            existing_mappings = self.get_existing_mapping()

            # 4. 获取各学校现有的最大编号
            self.logger.info("开始获取学校最大编号...")
            try:
                school_max_numbers = self.get_school_max_numbers(existing_mappings)
            except Exception as e:
                self.logger.error("获取学校最大编号失败: {}".format(str(e)))
                raise

            #school_max_numbers = self.get_school_max_numbers(unique_schools)
            self.logger.info("各学校当前最大编号：")
            for school, max_num in school_max_numbers.items():
                self.logger.info(f"{school}: {max_num}")
            # 5. 准备数据
            self.logger.info("开始生成映射记录...")
            mapping_records = []
            new_unified_ids = 0
            reused_unified_ids = 0
            current_school_numbers = school_max_numbers.copy()
            for school_name, school_group in df.groupby('school_name'):
                school_code = str(self.school_codes.get(school_name, '00000')).zfill(5)
                if len(school_code) != 5:
                    raise ValueError("学校编码 {} 必须是5位数".format(school_code))

                current_max = school_max_numbers[school_name]
                self.logger.info("\n处理学校：{} (代码:{}, 当前最大编号:{})".format(
                    school_name, school_code, current_max))

                for _, row in school_group.iterrows():
                    try:
                        # 检查是否存在已有映射
                        mapping_key = "{}_{}".format(row['school_name'], row['student_name'])

                        if mapping_key in existing_mappings:
                            unified_id = existing_mappings[mapping_key]
                            self.logger.info("复用已有统一考号: {} ({})".format(unified_id, mapping_key))
                            reused_unified_ids += 1
                            is_new = 0
                        else:
                            current_school_numbers[school_name] += 1
                            new_number = current_school_numbers[school_name]
                            if new_number > 9999:
                                raise ValueError(f"学校 {school_name} 的学生编号已超过最大值9999")

                            unified_id = f"25{school_code}{str(new_number).zfill(4)}"
                            existing_mappings[mapping_key] = unified_id
                            self.logger.info(f"分配新统一考号: {unified_id} ({mapping_key})")
                            new_unified_ids += 1
                            is_new = 1

                        # 添加映射记录
                        mapping_records.append({
                            'unified_id': unified_id,
                            'exam_id': exam_id,
                            'original_student_id': row['student_id'],
                            'student_name': row['student_name'],
                            'school_name': row['school_name'],
                            'class_name': row['class_name'],
                            'is_new': is_new
                        })

                    except Exception as e:
                        self.logger.error("处理学生记录时出错 - {} ({}): {}".format(
                            row['student_name'], row['student_id'], str(e)))
                        raise

                # 更新学校最大编号
                school_max_numbers[school_name] = current_max
                self.logger.info("学校 {} 最终编号: {}".format(school_name, current_max))

            # 6. 创建结果DataFrame并保存
            result_df = pd.DataFrame(mapping_records)

            # 7. 保存为Excel
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = "mapping_results_{}_{}.xlsx".format(exam_id, timestamp)

            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                result_df.to_excel(writer, sheet_name='映射数据', index=False)

                workbook = writer.book
                worksheet = writer.sheets['映射数据']

                header_info = [
                    ['考试数据映射结果'],
                    ['考试ID: {}'.format(exam_id)],
                    ['处理时间: {}'.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))],
                    ['总记录数: {}'.format(len(mapping_records))],
                    ['复用统一考号数: {}'.format(reused_unified_ids)],
                    ['新生成统一考号数: {}'.format(new_unified_ids)],
                    [''],
                    ['字段说明:'],
                    ['unified_id: 统一考号(11位)'],
                    ['exam_id: 考试ID'],
                    ['original_student_id: 原始考号'],
                    ['student_name: 学生姓名'],
                    ['school_name: 学校名称'],
                    ['class_name: 班级名称'],
                    ['is_new: 是否新记录(1是/0否)']
                ]

                # 插入说明信息
                for row_num, info in enumerate(header_info, 1):
                    worksheet.insert_rows(row_num)
                    worksheet.cell(row=row_num, column=1, value=info[0])

                # 调整列宽
                for column in worksheet.columns:
                    max_length = 0
                    column = [cell for cell in column]
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(cell.value)
                        except:
                            pass
                    adjusted_width = (max_length + 2)
                    worksheet.column_dimensions[column[0].column_letter].width = adjusted_width

            self.logger.info("\n处理完成:")
            self.logger.info("总记录数: {}".format(len(mapping_records)))
            self.logger.info("复用统一考号数: {}".format(reused_unified_ids))
            self.logger.info("新生成统一考号数: {}".format(new_unified_ids))
            self.logger.info("结果已保存到: {}".format(output_file))

            return result_df

        except Exception as e:
            self.logger.error("处理考试数据时出错: {}".format(str(e)))
            import traceback
            self.logger.error("详细错误信息: {}".format(traceback.format_exc()))
            raise

    def print_mapping_stats(self, exam_id):
        """打印映射统计信息"""
        try:
            # 统计总人数
            total_query = f"""
                SELECT COUNT(DISTINCT unified_id) as total_students,
                       COUNT(*) as total_records
                FROM student_mapping
                WHERE exam_id = '{exam_id}'
            """
            stats = pd.read_sql(total_query, self.engine)

            self.logger.info(f"\n考试 {exam_id} 统计信息:")
            self.logger.info(f"学生总数: {stats['total_students'].iloc[0]}")
            self.logger.info(f"记录总数: {stats['total_records'].iloc[0]}")

            # 统计班级变动情况
            class_changes_query = """
                SELECT a.unified_id, a.student_name, 
                       GROUP_CONCAT(DISTINCT a.class_name ORDER BY a.exam_id) as class_history
                FROM student_mapping a
                WHERE a.unified_id IN (
                    SELECT unified_id 
                    FROM student_mapping 
                    WHERE exam_id = %s
                )
                GROUP BY a.unified_id, a.student_name
                HAVING COUNT(DISTINCT a.class_name) > 1
            """
            class_changes = pd.read_sql(class_changes_query, self.engine, params=[exam_id])

            if not class_changes.empty:
                self.logger.info("\n班级变动情况:")
                for _, row in class_changes.iterrows():
                    self.logger.info(f"统一考号: {row['unified_id']}")
                    self.logger.info(f"班级变动: {row['class_history']}")

        except Exception as e:
            self.logger.error(f"生成统计信息时出错: {str(e)}")

def validate_school_codes(self):
    """验证学校代码是否都是5位数"""
    invalid_codes = []
    for school, code in self.school_codes.items():
        if len(str(code).zfill(5)) != 5:
            invalid_codes.append((school, code))

    if invalid_codes:
        error_msg = "发现以下学校代码不是5位数：\n"
        for school, code in invalid_codes:
            error_msg += f"学校：{school}, 代码：{code}\n"
        raise ValueError(error_msg)

def validate_input_data(self, df):
    """验证输入数据的完整性和格式"""
    try:
        # 1. 基础必需字段
        basic_required = ['student_name', 'school_name', 'class_name']

        # 2. 标识字段（至少需要有一个）
        id_columns = ['student_id', 'id_number', 'exam_number']

        # 检查基础必需字段
        missing_basic = [col for col in basic_required if col not in df.columns]
        if missing_basic:
            raise ValueError(f"缺少必要的基础字段：{', '.join(missing_basic)}")

        # 检查标识字段（至少要有一个）
        available_ids = [col for col in id_columns if col in df.columns]
        if not available_ids:
            raise ValueError(f"必须至少包含以下标识字段之一：{', '.join(id_columns)}")

        # 记录可用的标识字段
        self.logger.info(f"可用的标识字段：{', '.join(available_ids)}")

        # 3. 检查空值
        for col in basic_required:
            null_count = df[col].isnull().sum()
            if null_count > 0:
                raise ValueError(f"{col} 字段有 {null_count} 条记录为空")

        # 4. 检查标识字段的完整性
        id_stats = {}
        for col in available_ids:
            valid_count = df[col].notna().sum()
            id_stats[col] = valid_count
            self.logger.info(f"{col}: {valid_count} 条有效记录")

        # 5. 数据类型转换和清理
        df = self.clean_input_data(df, available_ids)

        return df, id_stats

    except Exception as e:
        self.logger.error(f"数据验证失败: {str(e)}")
        raise


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

        # 用户输入  请输入考试数据文件路径:请输入考试ID:
        excel_path ="202408-DIST-H.xlsx "
        exam_id = "202408-DIST-H"

        # 处理考试数据
        result = mapper.process_exam_data(excel_path, exam_id)

        if result is not None:
            print("\n处理成功！")
            print(f"结果已保存到映射表中，并导出到Excel文件。")

    except Exception as e:
        print(f"程序执行出错: {str(e)}")