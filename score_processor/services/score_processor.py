#score_processor.py
import pandas as pd
from django.apps import apps
from django.db import models

# score_processor/services/score_processor.py
import pandas as pd
from django.apps import apps
from django.db import models


class ScoreProcessorService:
    def __init__(self, exam_id=None, base_subject_config=None):
        self.ExamUpload = apps.get_model('score_processor', 'ExamUpload')
        self.df = None
        self.school_level = self._get_school_level(exam_id)
        self.should_classify_track = self._should_classify_track(base_subject_config)

        # 定义学期枚举
        self.SEMESTERS = {
            'G1S1': '高一上',  # 不分科
            'G1S2': '高一下',  # 分科
            'G2S1': '高二上',  # 分科
            'G2S2': '高二下',  # 分科
            'G3S1': '高三上',  # 分科
            'G3S2': '高三下'  # 分科
        }

        # 初始化科目配置
        self.subjects_config = {
            'H': {
                'no_track': {  # 高一上学期配置（不分科）
                    'required': ['语文', '数学', '英语'],
                    'optional': ['物理', '化学', '生物', '政治', '历史', '地理'],
                    'optional_count': 0  # 全科计分
                },
                'with_track': {  # 分科配置
                    'required': ['语文', '数学', '英语'],
                    'track_required': {
                        'science': '物理',
                        'arts': '历史'
                    },
                    'optional': ['化学', '生物', '政治', '地理'],
                    'optional_count': 2
                }
            },
            'M': {  # 初中配置
                'required': ['语文', '数学', '英语'],
                'optional': ['物理', '化学', '政治', '历史', '地理', '生物'],
                'optional_count': 0
            },
            'P': {  # 小学配置
                'required': ['语文', '数学', '英语'],
                'optional': ['科学', '品德'],
                'optional_count': 0
            }
        }

        # 设置当前配置
        if self.school_level == 'H':
            self.current_config = (self.subjects_config['H']['no_track']
                                   if not self.should_classify_track
                                   else self.subjects_config['H']['with_track'])
        else:
            self.current_config = self.subjects_config[self.school_level]

    def _get_school_level(self, exam_id):
        """从考试ID获取学段信息"""
        if not exam_id:
            return 'H'  # 默认为高中
        try:
            # 假设考试ID格式为: YYYYMM[H/M/P]XXX
            level = exam_id[6]
            if level in ['H', 'M', 'P']:
                return level
            return 'H'
        except:
            return 'H'

    def _should_classify_track(self, base_subject_config):
        """
        判断是否需要分科
        返回：True - 需要分科，False - 不分科
        """
        if not base_subject_config or self.school_level != 'H':
            return False

        try:
            # 直接根据学期判断是否分科
            semester = base_subject_config.semester
            # 只有高一上不分科
            return semester != 'G1S1'

        except Exception as e:
            print(f"分科判断错误: {str(e)}")
            return True  # 出错时默认分科

    def load_file(self, file):
        """加载并验证Excel文件"""
        try:
            self.df = pd.read_excel(file)

            # 获取当前学段所需的所有列
            required_columns = (
                    self.current_config['required'] +
                    ([] if not self.current_config.get('track_required') else
                     list(self.current_config['track_required'].values())) +
                    self.current_config['optional'] +
                    ['姓名', '考号', '班级']
            )

            missing_columns = [col for col in required_columns if col not in self.df.columns]
            if missing_columns:
                return False, f"缺少必需的列: {', '.join(missing_columns)}"

            # 验证数据格式
            for subject in required_columns[:-3]:  # 排除姓名、考号、班级
                self.df[subject] = pd.to_numeric(self.df[subject], errors='coerce')

            return True, None

        except Exception as e:
            return False, f"文件加载失败: {str(e)}"

    def determine_subject_type(self, scores):
        """判定文理科（仅高中分科时）"""
        if not self.should_classify_track:
            return '不分科'

        try:
            if not self.current_config.get('track_required'):
                return '不分科'

            science_subject = self.current_config['track_required']['science']
            arts_subject = self.current_config['track_required']['arts']

            is_science = scores[science_subject] > 0
            is_arts = scores[arts_subject] > 0

            if is_science and not is_arts:
                valid_optional_count = sum(
                    1 for subject in self.current_config['optional']
                    if scores.get(subject, -2) > 0
                )
                return '理科' if valid_optional_count >= self.current_config['optional_count'] else '未确定'

            elif is_arts and not is_science:
                valid_optional_count = sum(
                    1 for subject in self.current_config['optional']
                    if scores.get(subject, -2) > 0
                )
                return '文科' if valid_optional_count >= self.current_config['optional_count'] else '未确定'

            return '未确定'

        except Exception as e:
            print(f"科类判定错误: {str(e)}")
            return '未确定'

    def calculate_total_score(self, scores, subject_type):
        """计算总分，优先使用上传文件中的总分字段"""
        try:
            # 检查是否存在总分字段
            if '总分' in scores and scores['总分'] > 0:
                return scores['总分']

            total = 0

            # 如果没有总分字段，则按规则计算
            # 计算必修科目总分
            for subject in self.current_config['required']:
                score = scores.get(subject, -1)
                if score <= 0:
                    return -1
                total += score

            if self.should_classify_track:
                # 高中分科时的处理
                if subject_type == '理科':
                    physics_score = scores.get(self.current_config['track_required']['science'], -1)
                    if physics_score <= 0:
                        return -1
                    total += physics_score
                elif subject_type == '文科':
                    history_score = scores.get(self.current_config['track_required']['arts'], -1)
                    if history_score <= 0:
                        return -1
                    total += history_score
                elif subject_type == '未确定':
                    return -1

                # 计算选考科目成绩
                optional_scores = []
                for subject in self.current_config['optional']:
                    score = scores.get(subject, -2)
                    if score > 0:
                        optional_scores.append(score)

                # 取最高的指定数量选考科目
                optional_scores.sort(reverse=True)
                if len(optional_scores) >= self.current_config['optional_count']:
                    total += sum(optional_scores[:self.current_config['optional_count']])
                else:
                    return -1
            else:
                # 不分科时：所有科目都计入总分
                for subject in self.current_config['optional']:
                    score = scores.get(subject, 0)
                    if score > 0:  # 只计入有效成绩
                        total += score

            return total

        except Exception as e:
            print(f"总分计算错误: {str(e)}")
            return -1

    def process_scores(self, df, upload_id=None):
        """处理成绩数据"""
        upload = None
        if upload_id:
            try:
                upload = self.ExamUpload.objects.get(id=upload_id)
                upload.status = 'PROCESSING'
                upload.save()
            except self.ExamUpload.DoesNotExist:
                print(f"Warning: Upload record {upload_id} not found")

        try:
            results = []
            stats = {
                '总人数': len(df),
                '有效总分人数': 0
            }

            # 高中分科时才需要统计文理科人数
            if self.should_classify_track:
                stats.update({
                    '理科人数': 0,
                    '文科人数': 0,
                    '未确定人数': 0
                })

            total_rows = len(df)
            processed_rows = 0

            for _, row in df.iterrows():
                scores = row.to_dict()

                # 判定文理科（仅高中分科时）
                subject_type = self.determine_subject_type(scores)
                if self.should_classify_track:
                    stats[f'{subject_type}人数'] += 1

                # 计算总分
                total_score = self.calculate_total_score(scores, subject_type)
                if total_score > 0:
                    stats['有效总分人数'] += 1

                result = {
                    'student_name': scores.get('姓名', ''),
                    'student_id': scores.get('考号', ''),
                    'class_name': scores.get('班级', ''),
                    'subject_type': subject_type,
                    'total_score': total_score
                }

                # 添加所有科目成绩
                for subject in (self.current_config['required'] +
                                ([] if not self.current_config.get('track_required') else
                                list(self.current_config['track_required'].values())) +
                                self.current_config['optional']):
                    result[subject] = scores.get(subject, -1)

                results.append(result)

                # 更新进度
                processed_rows += 1
                if upload and processed_rows % 100 == 0:
                    progress = int(processed_rows / total_rows * 100)
                    upload.error_message = f"处理进度: {progress}%"
                    upload.save()

            # 保存统计信息
            if upload:
                upload.status = 'COMPLETED'
                stats_message = f"""处理完成
                总人数: {stats['总人数']}
                有效总分: {stats['有效总分人数']}"""

                if self.should_classify_track:
                    stats_message += f"""
                    理科: {stats['理科人数']}
                    文科: {stats['文科人数']}
                    未确定: {stats['未确定人数']}"""

                upload.error_message = stats_message
                upload.save()

            return {
                'success': True,
                'results': results,
                'stats': stats
            }

        except Exception as e:
            error_msg = f"成绩处理错误: {str(e)}"
            print(error_msg)

            if upload:
                upload.status = 'FAILED'
                upload.error_message = error_msg
                upload.save()

            return {
                'success': False,
                'error': str(e)
            }

    def validate_file(self, file):
        """验证上传的文件"""
        try:
            df = pd.read_excel(file)
            required_columns = ['姓名', '考号', '班级'] + self.current_config['required']
            return all(col in df.columns for col in required_columns)
        except Exception:
            return False

    def get_preview_data(self):
        """获取预览数据"""
        if self.df is None:
            return None

        try:
            result = self.process_scores(self.df)
            if result['success']:
                preview_data = pd.DataFrame(result['results']).head(10)
                return {
                    'data': preview_data,
                    'stats': result['stats']
                }
            return None
        except Exception as e:
            print(f"获取预览数据失败: {str(e)}")
            return None