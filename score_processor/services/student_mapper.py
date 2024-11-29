# score_processor/services/student_mapper.py

from ..models import StudentMapping, BaseSchoolInfo
import pandas as pd


class StudentMapperService:
    def __init__(self):
        self.school_codes = self._load_school_codes()
        self.existing_mappings = self._load_existing_mappings()
        self.school_sequences = {}
        print("初始化结果:")  # debug信息
    #   print(f"加载的学校代码: {self.school_codes}")
        print(f"加载的现有映射: {self.existing_mappings}")

    def _load_existing_mappings(self):
        """加载现有的学生映射"""
        try:
            mappings = {}
            existing = StudentMapping.objects.all()

            if not existing.exists():
                print("警告: 还没有任何学生映射记录")
                return {}

            for item in existing:
                key = f"{item.school_name}_{item.student_name}"
                mappings[key] = item.unified_id

            return mappings

        except Exception as e:
            print(f"加载现有映射出错: {str(e)}")
            return {}

    def _load_school_codes(self):
        """加载学校代码表"""
        try:
            school_codes = {}
            schools = BaseSchoolInfo.objects.all()

            if not schools.exists():
                print("警告: 学校信息表为空")
                # 如果表为空，可以返回一个空字典，后面会动态生成学校代码
                return {}

            for school in schools:
                school_codes[school.school_name] = school.school_code
            return school_codes

        except Exception as e:
            print(f"加载学校代码出错: {str(e)}")
            return {}

    def _generate_school_code(self, school_name):
        """动态生成学校代码"""
        # 如果base_school_info为空，我们可以动态生成一个简单的学校代码
        if school_name not in self.school_codes:
            # 使用一个简单的规则生成学校代码（这里用学校名的前5个字符的编码）
            code = str(abs(hash(school_name)) % 100000).zfill(5)
            self.school_codes[school_name] = code
            print(f"为学校 {school_name} 生成代码: {code}")
        return self.school_codes[school_name]

    def process_exam_data(self, df, exam_id):
        """处理考试数据，生成统一ID映射"""
        try:
            print("开始处理考试数据...")
            # 确保考号为字符串类型
            df['考号'] = df['考号'].astype(str)
            # 1. 先处理同校不同班重名
            print("处理同校不同班重名...")
            df = self.handle_name_duplicates(df)
            print("同校重名处理完成")

            # 2. 再检查是否有同班重名（这是错误情况）
            has_duplicates, error_msg = self.check_same_class_duplicates(df)
            if has_duplicates:
                print(f"发现同班重名: {error_msg}")
                raise ValueError(f"发现同班重名学生:\n{error_msg}")
            print("重名检查完成")

            # 生成或获取统一ID
            new_count = 0  # 新增计数器
            reused_count = 0  # 复用计数器
            new_mappings = []
            mapping_dict = {}  # 用于存储生成的映射关系

            for _, row in df.iterrows():
                try:
                    key = f"{row['学校']}_{row['姓名']}"

                    if key in self.existing_mappings:
                        unified_id = self.existing_mappings[key]
                        reused_count += 1
                        print(f"使用已有ID: {key} -> {unified_id}")
                    else:
                        unified_id = self.generate_unified_id(row['学校'])
                        self.existing_mappings[key] = unified_id
                        new_count += 1
                        print(f"生成新ID: {key} -> {unified_id}")

                    mapping_dict[row['考号']] = unified_id  # 存储考号和统一ID的对应关系

                    mapping = StudentMapping(
                        unified_id=unified_id,
                        exam_id=exam_id,
                        original_student_id=str(row['考号']),
                        student_name=row['姓名'],
                        school_name=row['学校'],
                        class_name=row['班级']
                    )
                    new_mappings.append(mapping)

                except Exception as e:
                    print(f"处理学生记录时出错 - {row['姓名']}: {str(e)}")
                    continue

                    # 批量保存映射前添加调试信息
                print(f"准备保存映射记录，总数：{len(new_mappings)}")
                print("映射示例：")

                for mapping in new_mappings[:5]:  # 显示前5条记录
                    print(f"考号: {mapping.original_student_id} -> 统一ID: {mapping.unified_id}")
            # 批量保存映射
            StudentMapping.objects.bulk_create(new_mappings)

            # 在原始数据中添加统一ID列
            df['统一ID'] = df['考号'].map(mapping_dict)

            return {
                'success': True,
                'total_count': len(new_mappings),
                'new_count': new_count,
                'reused_count': reused_count,
                'preview_df': df  # 返回带有统一ID的DataFrame
            }

        except Exception as e:
            print(f"处理考试数据时出错: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def check_same_class_duplicates(self, df):
        """检查同班重名情况"""
        try:
            print("检查同班重名...")
            duplicates = df.groupby(['学校', '班级', '姓名']).size()
            duplicates = duplicates[duplicates > 1]

            if not duplicates.empty:
                error_messages = []
                for (school, class_name, name), count in duplicates.items():
                    error_messages.append(
                        f"学校: {school}, 班级: {class_name}, "
                        f"姓名: {name}, 重复次数: {count}"
                    )
                return True, "\n".join(error_messages)

            return False, ""

        except Exception as e:
            print(f"检查重名出错: {str(e)}")
            return False, str(e)

    def handle_name_duplicates(self, df):
        """处理重名情况"""
        try:
            print("处理学生重名...")
            # 1. 先处理同校重名，添加班级后缀
            school_duplicates = df.groupby(['学校', '姓名']).size()
            school_duplicates = school_duplicates[school_duplicates > 1]

            for (school, name) in school_duplicates.index:
                mask = (df['学校'] == school) & (df['姓名'] == name)
                dup_records = df[mask]

                for idx, row in dup_records.iterrows():
                    # 获取班级号（最后两位数字）
                    class_name = str(row['班级'])
                    digits = ''.join(filter(str.isdigit, class_name))
                    class_num = digits[-2:].zfill(2) if len(digits) > 0 else '00'

                    new_name = f"{name}_{class_num}"
                    df.loc[idx, '姓名'] = new_name
                    print(f"重名处理第一步: {name} -> {new_name}")

            # 2. 处理同班重名，添加序号
            class_duplicates = df.groupby(['学校', '班级', '姓名']).size()
            class_duplicates = class_duplicates[class_duplicates > 1]

            for (school, class_name, name) in class_duplicates.index:
                mask = (df['学校'] == school) & (df['班级'] == class_name) & (df['姓名'] == name)
                dup_records = df[mask]

                for num, (idx, _) in enumerate(dup_records.iterrows(), 1):
                    new_name = f"{name}_{str(num).zfill(2)}"
                    df.loc[idx, '姓名'] = new_name
                    print(f"重名处理第二步: {name} -> {new_name}")

            return df

        except Exception as e:
            print(f"处理重名出错: {str(e)}")
            return df

    def generate_unified_id(self, school_name):
        """生成新的统一ID"""
        try:
            # 生成或获取学校代码
            if school_name not in self.school_codes:
                code = str(abs(hash(school_name)) % 100000).zfill(5)
                self.school_codes[school_name] = code
                print(f"为学校 {school_name} 生成代码: {code}")

            school_code = self.school_codes[school_name]

            # 获取或初始化该学校的序号
            if school_name not in self.school_sequences:
                last_id = StudentMapping.objects.filter(
                    unified_id__startswith=f"25{school_code}"
                ).order_by('-unified_id').first()

                if last_id:
                    last_num = int(last_id.unified_id[-4:])
                    self.school_sequences[school_name] = last_num
                else:
                    self.school_sequences[school_name] = 0

            # 序号加1
            self.school_sequences[school_name] += 1
            sequence = str(self.school_sequences[school_name]).zfill(4)

            # 组合统一ID: 25 + 学校代码(5位) + 序号(4位)
            unified_id = f"25{school_code}{sequence}"
            print(f"生成统一ID: {unified_id}")
            return unified_id

        except Exception as e:
            print(f"生成统一ID出错: {str(e)}")
            raise

    def _get_school_max_sequence(self, school_code):
        """获取学校当前最大序号"""
        try:
            last_id = StudentMapping.objects.filter(
                unified_id__startswith=f"25{school_code}"
            ).order_by('-unified_id').first()

            if last_id:
                return int(last_id.unified_id[-4:])
            return 0
        except Exception as e:
            print(f"获取学校序号出错: {str(e)}")
            return 0