#score_processor.py
import pandas as pd
from django.apps import apps
from django.db import models


class ScoreProcessorService:
    def __init__(self):
        self.ExamUpload = apps.get_model('score_processor', 'ExamUpload')
        # 科目定义
        self.required_subjects = ['语文', '数学', '英语']
        self.science_subject = '物理'  # 理科必选
        self.arts_subject = '历史'  # 文科必选
        self.optional_subjects = ['化学', '生物', '政治', '地理']
        self.df = None

    def load_file(self, file):
        """
        加载并验证Excel文件
        返回: (成功/失败, 错误信息)
        """
        try:
            self.df = pd.read_excel(file)

            # 验证必需的列
            required_columns = self.required_subjects + [self.science_subject, self.arts_subject] + \
                               self.optional_subjects + ['姓名', '考号', '班级']

            missing_columns = [col for col in required_columns if col not in self.df.columns]
            if missing_columns:
                return False, f"缺少必需的列: {', '.join(missing_columns)}"

            # 验证数据格式
            for subject in self.required_subjects + [self.science_subject, self.arts_subject] + self.optional_subjects:
                self.df[subject] = pd.to_numeric(self.df[subject], errors='coerce')

            return True, None

        except Exception as e:
            return False, f"文件加载失败: {str(e)}"

    def determine_subject_type(self, scores):
        """
        判定文理科
        返回：'理科', '文科' 或 '未确定'
        """
        try:
            # 判断物理或历史成绩是否有效（大于0）
            is_science = scores[self.science_subject] > 0
            is_arts = scores[self.arts_subject] > 0

            if is_science and not is_arts:
                # 选考物理，判定为理科
                valid_optional_count = sum(
                    1 for subject in self.optional_subjects
                    if scores.get(subject, -2) > 0
                )
                return '理科' if valid_optional_count >= 2 else '未确定'

            elif is_arts and not is_science:
                # 选考历史，判定为文科
                valid_optional_count = sum(
                    1 for subject in self.optional_subjects
                    if scores.get(subject, -2) > 0
                )
                return '文科' if valid_optional_count >= 2 else '未确定'

            return '未确定'

        except Exception as e:
            print(f"科类判定错误: {str(e)}")
            return '未确定'

    def calculate_total_score(self, scores, subject_type):
        """
        计算总分
        根据科类选择相应科目计算
        """
        try:
            total = 0
            # 必修科目
            for subject in self.required_subjects:
                score = scores.get(subject, -1)
                if score <= 0:  # 缺考或无效成绩
                    return -1
                total += score

            # 根据科类判断必选科目
            if subject_type == '理科':
                physics_score = scores.get(self.science_subject, -1)
                if physics_score <= 0:
                    return -1
                total += physics_score
            elif subject_type == '文科':
                history_score = scores.get(self.arts_subject, -1)
                if history_score <= 0:
                    return -1
                total += history_score
            else:
                return -1

            # 计算选考科目成绩
            optional_scores = []
            for subject in self.optional_subjects:
                score = scores.get(subject, -2)
                if score > 0:
                    optional_scores.append(score)

            # 取最高的两门选考科目
            optional_scores.sort(reverse=True)
            if len(optional_scores) >= 2:
                total += sum(optional_scores[:2])
            else:
                return -1

            return total

        except Exception as e:
            print(f"总分计算错误: {str(e)}")
            return -1

    def process_scores(self, df, upload_id=None):
        """
        处理成绩数据
        upload_id: ExamUpload记录的ID
        """
        upload = None
        if upload_id:
            try:
                upload = self.ExamUpload.objects.get(id=upload_id)
                upload.status = 'PROCESSING'
                upload.save()
            except self.ExamUpload.DoesNotExist:
                print(f"Warning: Upload record {upload_id} not found")

        try:
            print("开始处理成绩数据...")  # 调试信息
            results = []
            stats = {
                '总人数': len(df),
                '理科人数': 0,
                '文科人数': 0,
                '未确定人数': 0,
                '有效总分人数': 0,
            }

            total_rows = len(df)
            processed_rows = 0

            for _, row in df.iterrows():
                # 转换行数据为字典
                scores = row.to_dict()

                # 判定文理科
                subject_type = self.determine_subject_type(scores)
                stats[f'{subject_type}人数'] += 1

                # 计算总分
                total_score = self.calculate_total_score(scores, subject_type)
                if total_score > 0:
                    stats['有效总分人数'] += 1

                results.append({
                    'student_name': scores.get('姓名', ''),
                    'subject_type': subject_type,
                    'total_score': total_score,
                    **{subject: scores.get(subject, -1) for subject in self.required_subjects},
                    **{subject: scores.get(subject, -2) for subject in self.optional_subjects}
                })

                # 更新进度
                processed_rows += 1
                if upload and processed_rows % 100 == 0:  # 每处理100条更新一次状态
                    progress = int(processed_rows / total_rows * 100)
                    upload.error_message = f"处理进度: {progress}%"
                    upload.save()

            print("成绩处理完成")  # 调试信息

            # 保存统计信息
            if upload:
                upload.status = 'COMPLETED'
                upload.error_message = f"""处理完成
    总人数: {stats['总人数']}
    理科: {stats['理科人数']}
    文科: {stats['文科人数']}
    未确定: {stats['未确定人数']}
    有效总分: {stats['有效总分人数']}"""
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
# 添加新的辅助方法
    def validate_file(self, file):
        """验证上传的文件"""
        try:
            df = pd.read_excel(file)
            required_columns = ['姓名', '考号', '班级', '语文', '数学', '英语']
            return all(col in df.columns for col in required_columns)
        except Exception:
            return False

    def get_preview_data(self):
        """
        获取预览数据
        返回: 处理结果的前10行和统计信息
        """
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