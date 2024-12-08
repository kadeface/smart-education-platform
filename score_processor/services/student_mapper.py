# score_processor/services/student_mapper.py
import pandas as pd

from ..models import StudentMapping, BaseSchoolInfo
#import pandas as pd


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
           # print(f"为学校 {school_name} 生成代码: {code}")
        return self.school_codes[school_name]

    def process_exam_data(self, df, exam_id):
        """处理考试数据，生成统一ID映射"""
        try:
            # 确保考号为字符串类型
            df['考号'] = df['考号'].astype(str)

            # 处理重名
            df = self.handle_name_duplicates(df)

            # 清理已有记录
            StudentMapping.objects.filter(exam_id=exam_id).delete()
            print(f"已清理现有映射记录: exam_id={exam_id}")

            # 生成新映射
            new_mappings = []
            mapping_dict = {}
            stats = {'new': 0, 'reused': 0}

            for idx, row in df.iterrows():
                try:
                    school_name = str(row['学校'])
                    student_name = str(row['姓名'])
                    key = f"{school_name}_{student_name}"

                    # 获取或生成统一ID
                    if key in self.existing_mappings:
                        unified_id = self.existing_mappings[key]
                        stats['reused'] += 1
                    else:
                        unified_id = self.generate_unified_id(school_name)
                        self.existing_mappings[key] = unified_id
                        stats['new'] += 1

                    # 创建映射记录
                    mapping = StudentMapping(
                        unified_id=unified_id,
                        exam_id=exam_id,
                        original_student_id=str(row['考号']),
                        student_name=student_name,
                        school_name=school_name,
                        class_name=str(row['班级'])
                    )
                    new_mappings.append(mapping)
                    mapping_dict[str(row['考号'])] = unified_id

                except Exception as e:
                    print(f"处理单条记录时出错 - 索引{idx}: {str(e)}")

            # 保存映射记录
            if new_mappings:
                StudentMapping.objects.bulk_create(new_mappings)
                print(f"保存了{len(new_mappings)}条映射记录")

                # 添加统一ID列
                df['统一ID'] = df['考号'].map(mapping_dict)

                # 写入score_student_basic表
                from score_processor.models import ScoreStudentBasic

                # 先删除已有记录
                ScoreStudentBasic.objects.filter(exam_id=exam_id).delete()

                student_records = []
                for _, row in df.iterrows():
                    try:
                        # 处理可能的nan值
                        def safe_float(value):
                            return float(value) if pd.notnull(value) and value != 'nan' else 0.0

                        student_record = ScoreStudentBasic(
                            exam_id=exam_id,
                            student_id=row['统一ID'],
                            student_name=row['姓名'],
                            district_name=row['市区'],
                            school_name=row['学校'],
                            class_field=str(row['班级']),
                            select_type='理科' if safe_float(row.get('物理', 0)) > 0 else '文科',
                            chinese=safe_float(row.get('语文', 0)),
                            math=safe_float(row.get('数学', 0)),
                            english=safe_float(row.get('英语', 0)),
                            physics=safe_float(row.get('物理', 0)),
                            chemistry=safe_float(row.get('化学', 0)),
                            biology=safe_float(row.get('生物', 0)),
                            history=safe_float(row.get('历史', 0)),
                            politics=safe_float(row.get('政治', 0)),
                            geography=safe_float(row.get('地理', 0)),
                            total_score=0  # 总分后续计算
                        )
                        student_records.append(student_record)
                    except Exception as e:
                        print(f"处理学生记录时出错: {str(e)}")
                        continue

                if student_records:
                    ScoreStudentBasic.objects.bulk_create(student_records)
                    print(f"保存了{len(student_records)}条学生成绩记录")

                return {
                    'success': True,
                    'total_count': len(new_mappings),
                    'new_count': stats['new'],
                    'reused_count': stats['reused'],
                    'preview_df': df
                }
            else:
                return {
                    'success': False,
                    'error': "未生成任何映射记录"
                }

        except Exception as e:
            print(f"处理考试数据时发生错误: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }
    def check_same_class_duplicates(self, df):
        """检查同班重名情况"""
        try:
            print("检查同班重名...")
            # 分组计数
            duplicate_mask = df.groupby(['学校', '班级', '姓名']).size()
            duplicate_rows = duplicate_mask[duplicate_mask > 1]

            if not duplicate_rows.empty:  # 使用.empty替代直接布尔判断
                error_messages = []
                for (school, class_name, name), count in duplicate_rows.items():
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
            print("开始处理重名...")
            print(f"输入数据形状: {df.shape}")
            print("输入数据列: ", df.columns.tolist())

            # 1. 先处理同校重名
            school_names = df.groupby(['学校', '姓名']).size()
            duplicates = school_names[school_names > 1]

            if len(duplicates) > 0:  # 使用len()而不是直接判断
                print(f"发现{len(duplicates)}个同校重名")
                for (school, name), count in duplicates.items():
                    # 找到该校该名字的所有记录
                    rows = df[
                        (df['学校'].astype(str) == str(school)) &
                        (df['姓名'].astype(str) == str(name))
                        ]

                    print(f"处理重名: 学校={school}, 姓名={name}, 共{len(rows)}条记录")

                    # 为每条记录添加班级后缀
                    for idx in rows.index:
                        class_name = str(df.at[idx, '班级'])
                        class_num = ''.join(filter(str.isdigit, class_name))[-2:].zfill(2)
                        new_name = f"{name}_{class_num}"
                        df.at[idx, '姓名'] = new_name
                        print(f"重命名: {name} -> {new_name}")

            # 2. 再检查班级内重名
            class_names = df.groupby(['学校', '班级', '姓名']).size()
            class_duplicates = class_names[class_names > 1]

            if len(class_duplicates) > 0:  # 使用len()而不是直接判断
                print(f"发现{len(class_duplicates)}个班级内重名")
                for (school, class_name, name), count in class_duplicates.items():
                    # 找到该班级该名字的所有记录
                    rows = df[
                        (df['学校'].astype(str) == str(school)) &
                        (df['班级'].astype(str) == str(class_name)) &
                        (df['姓名'].astype(str) == str(name))
                        ]

                    print(f"处理班级重名: 学校={school}, 班级={class_name}, 姓名={name}")

                    # 为每条记录添加序号
                    for i, idx in enumerate(rows.index, 1):
                        new_name = f"{df.at[idx, '姓名']}_{str(i).zfill(2)}"
                        df.at[idx, '姓名'] = new_name
                        print(f"重命名: {name} -> {new_name}")

            return df

        except Exception as e:
            print(f"处理重名时发生错误: {str(e)}")
            import traceback
            print(traceback.format_exc())
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