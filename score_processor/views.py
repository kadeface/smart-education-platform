import numpy as np
from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect
from .models import ScoreStudentBasic, StudentMapping
from .forms import ScoreUploadForm
from .services.student_mapper import StudentMapperService
import pandas as pd
from.models import ExamUpload
from .services.data_cleaner import DataCleanerService
import openpyxl
from django.contrib import messages
# 在 oldviews.py 或 score_analysis.py 中
from score_processor.services.score_processor import ScoreProcessorService
def score_list(request):
    # 获取所有成绩记录
    scores = ScoreStudentBasic.objects.all()[:10]  # 先只取前10条数据
    return render(request, 'score_processor/score_list.html', {'scores': scores})


def upload_scores(request):
    if request.method == 'POST':
        form = ScoreUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                file = request.FILES['file']
                exam_id = form.cleaned_data['exam_id']
                # 保存上传文件
                upload = ExamUpload.objects.create(
                    file=file,
                    exam_id=exam_id
                )
                request.session['upload_id'] = upload.id
                request.session['exam_id'] = exam_id
                print(f"保存到session - upload_id: {upload.id}, exam_id: {exam_id}")  # 调试信息

                # 读取Excel文件
                df = pd.read_excel(file)

                # 1. 修正列名中的空格
                df = df.rename(columns={'英语听 说': '英语听说'})

                # 2. 确保成绩列为float类型
                score_columns = ['语文', '数学', '英语', '物理', '化学', '生物',
                                 '历史', '政治', '地理', '英语听说']
                for col in score_columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

                # 3. 判断文理科
                def determine_type(row):
                    # 选考科目
                    optional_subjects = ['化学', '生物', '政治', '地理']
                    optional_scores = [row[subject] for subject in optional_subjects]
                    valid_subjects = sum(pd.notna(score) and score > 0 for score in optional_scores)

                    # 理科判断
                    if pd.notna(row['物理']) and row['物理'] > 0:
                        if valid_subjects >= 2:  # 至少有2个选考科目
                            return '理科'
                        return '未确定'

                    # 文科判断
                    elif pd.notna(row['历史']) and row['历史'] > 0:
                        if valid_subjects >= 2:  # 至少有2个选考科目
                            return '文科'
                        return '未确定'

                    return '未确定'

                df['科类'] = df.apply(determine_type, axis=1)
                # 4. 填充NaN值为0
                for col in score_columns:
                    df[col] = df[col].fillna(0)

                # 5. 计算统计信息
                stats = {
                    '总人数': len(df),
                    '理科人数': len(df[df['科类'] == '理科']),
                    '文科人数': len(df[df['科类'] == '文科']),
                    '未确定人数': len(df[df['科类'] == '未确定']),
                    '语文平均分': round(df['语文'].mean(), 2),
                    '数学平均分': round(df['数学'].mean(), 2),
                    '英语平均分': round(df['英语'].mean(), 2)
                }
                # 保存上传ID到session
                request.session['upload_id'] = upload.id
                # 打印统计信息
                print("\n数据统计:")
                for key, value in stats.items():
                    print(f"{key}: {value}")

                # 打印处理后的数据预览
                print("\n处理后的数据预览:")
                print(df.head())

                # 将数据传递到模板
                return render(request, 'score_processor/preview.html', {
                    'preview': df.head(10).to_html(index=False),
                    'stats': stats,
                    'exam_id': exam_id
                })

            except Exception as e:
                print(f"上传文件处理错误: {str(e)}")
                messages.error(request, f'处理文件时出错：{str(e)}')
                return redirect('score_processor:upload_scores')
    else:
        form = ScoreUploadForm()

    return render(request, 'score_processor/upload.html', {'form': form})
def confirm_import(request):
    if request.method == 'POST':
        # 这里添加实际的数据导入逻辑
        pass
    return redirect('score_processor:score_list')


def start_mapping(request):
    """开始ID映射的视图"""
    if request.method == 'POST':
        upload_id = request.session.get('upload_id')
        cleaned_file_path = request.session.get('cleaned_file_path')
        exam_id = request.POST.get('exam_id')  # 从表单获取exam_id

        print(f"Debug - exam_id: {exam_id}")  # 调试信息

        if not all([upload_id, cleaned_file_path, exam_id]):
            messages.error(request, '无法获取必要的处理信息')
            return redirect('score_processor:upload_scores')

        try:
            # 读取清洗后的数据
            df = pd.read_excel(cleaned_file_path)

            # 进行ID映射
            mapper = StudentMapperService()
            mapping_result = mapper.process_exam_data(df, exam_id)  # 使用从表单获取的exam_id

            if not mapping_result['success']:
                error_msg = mapping_result['error']
                return render(request, 'score_processor/error.html', {
                    'error_title': '生成统一ID时出错',
                    'error_detail': error_msg,
                    'exam_id': exam_id  # 传递exam_id到错误页面
                })

            # 显示映射结果
            mapping_stats = {
                '总记录数': mapping_result['total_count'],
                '新生成统一ID数': mapping_result['new_count'],
                '复用统一ID数': mapping_result['reused_count']
            }

            # 使用包含统一ID的DataFrame创建预览
            preview_df = mapping_result['preview_df']
            preview_html = preview_df.head(10).to_html(index=False)

            # 保存exam_id到session以供后续使用
            request.session['exam_id'] = exam_id

            return render(request, 'score_processor/mapping_result.html', {
                'exam_id': exam_id,
                'stats': mapping_stats,
                'preview': preview_html
            })

        except Exception as e:
            print(f"映射错误: {str(e)}")  # 调试信息
            messages.error(request, f'生成统一ID时出错：{str(e)}')
            return redirect('score_processor:upload_scores')

    return redirect('upload_scores')


def clean_data(self, request, upload_id):
    """清洗数据"""
    try:
        upload = self.get_object(request, upload_id)
        processor = ScoreProcessorService()
        cleaner = DataCleanerService()

        if request.method == 'POST':
            # 加载数据
            success, error = processor.load_file(upload.file.path)
            if not success:
                messages.error(request, f"文件加载失败: {error}")
                return redirect('score_analysis:score_processor_examupload_changelist')

            # 清洗数据
            result = cleaner.clean_data(processor.df)
            if result['success']:
                upload.status = 'PROCESSING'  # 继续处理
                upload.save()

                # 将清洗统计转换为普通Python类型
                cleaning_stats = result['stats']
                for key, value in cleaning_stats.items():
                    if isinstance(value, np.int64):
                        cleaning_stats[key] = int(value)
                    elif isinstance(value, dict):
                        for k, v in value.items():
                            if isinstance(v, np.int64):
                                value[k] = int(v)

                # 获取有效成绩统计并转换类型
                score_stats = cleaner.get_valid_scores_stats(result['cleaned_df'])

                context = {
                    'title': '数据清洗',
                    'subtitle': '数据清洗完成',
                    'opts': self.model._meta,
                    'upload': upload,
                    'has_view_permission': True,
                    'cleaning_stats': cleaning_stats,
                    'score_stats': score_stats,
                }

                messages.success(request, "数据清洗完成")
                return render(request, 'score_processor/cleaning.html', context)
            else:
                upload.status = 'FAILED'
                upload.error_message = result.get('error', '未知错误')
                upload.save()
                messages.error(request, f"清洗失败: {result.get('error', '未知错误')}")

        # GET请求显示清洗页面
        context = {
            'title': '数据清洗',
            'subtitle': '点击开始清洗按钮进行数据清洗',
            'opts': self.model._meta,
            'upload': upload,
            'has_view_permission': True,
        }
        return render(request, 'score_processor/cleaning.html', context)

    except Exception as e:
        messages.error(request, f"清洗数据失败: {str(e)}")
        return redirect('score_analysis:score_processor_examupload_changelist')


def save_scores(request):
    """保存处理后的成绩数据"""
    if request.method == 'POST':
        cleaned_file_path = request.session.get('cleaned_file_path')
        exam_id = request.POST.get('exam_id')

        if not cleaned_file_path or not exam_id:
            messages.error(request, '无法获取处理所需的信息')
            return redirect('upload_scores')

        try:
            # 首先删除该考试的旧记录
            deleted_count = ScoreStudentBasic.objects.filter(exam_id=exam_id).delete()
            print(f"删除旧记录数: {deleted_count}")

            # 读取处理后的数据
            df = pd.read_excel(cleaned_file_path)

            # 获取该考试的统一ID映射
            id_mappings = StudentMapping.objects.filter(
                exam_id=exam_id
            ).values('original_student_id', 'unified_id')

            # 创建映射字典
            id_map = {
                str(m['original_student_id']): m['unified_id']
                for m in id_mappings
            }

            # 检查未匹配的考号
            unmatched_ids = []
            for _, row in df.iterrows():
                exam_id_str = str(row['考号'])
                if exam_id_str not in id_map:
                    unmatched_ids.append(exam_id_str)

            if unmatched_ids:
                print("\n未找到映射的考号（前10个）:")
                for exam_id_str in unmatched_ids[:10]:
                    print(f"- {exam_id_str}")
                raise ValueError(f"有 {len(unmatched_ids)} 个考号未找到对应的统一ID")
            # 创建待保存的记录列表
            score_records = []
            for _, row in df.iterrows():
                exam_id_str = str(row['考号'])
                unified_id = id_map.get(exam_id_str)

                # 判断文理科
                if row['物理'] > 0:
                    subject_type = '理科'
                    optional_subjects = ['化学', '生物', '政治', '地理']
                    required_subject_score = row['物理']
                elif row['历史'] > 0:
                    subject_type = '文科'
                    optional_subjects = ['政治', '地理', '化学', '生物']
                    required_subject_score = row['历史']
                else:
                    subject_type = '未确定'
                    required_subject_score = 0

                # 计算总分
                # 1. 必修科目
                calculated_total = row['语文'] + row['数学'] + row['英语']

                # 2. 必选科目（物理或历史）
                if required_subject_score > 0:
                    calculated_total += required_subject_score

                    # 3. 选考科目（取最高的两门）
                    optional_scores = []
                    for subject in optional_subjects:
                        score = row[subject]
                        if score > 0:  # 只计算有效成绩
                            optional_scores.append(score)

                    if len(optional_scores) >= 2:
                        optional_scores.sort(reverse=True)
                        calculated_total += optional_scores[0] + optional_scores[1]
                    else:
                        calculated_total = 0  # 选考科目不足两门，总分记为0
                else:
                    calculated_total = 0  # 无必选科目，总分记为0

                record = ScoreStudentBasic(
                    exam_id=exam_id,
                    student_id=unified_id,
                    student_name=row['姓名'],
                    district_name=row['市区'],
                    school_name=row['学校'],
                    class_field=row['班级'],
                    select_type=subject_type,
                    chinese=row['语文'],
                    math=row['数学'],
                    english=row['英语'],
                    physics=row['物理'],
                    chemistry=row['化学'],
                    biology=row['生物'],
                    history=row['历史'],
                    politics=row['政治'],
                    geography=row['地理'],
                    total_score=calculated_total  # 使用计算出的总分
                )
                score_records.append(record)

            # 批量保存记录
            ScoreStudentBasic.objects.bulk_create(score_records)
            # 打印一些统计信息
            print(f"\n保存完成：")
            print(f"总记录数：{len(score_records)}")
            valid_scores = [r.total_score for r in score_records if r.total_score > 0]
            if valid_scores:
                print(f"有效成绩数：{len(valid_scores)}")
                print(f"最高分：{max(valid_scores)}")
                print(f"最低分：{min(valid_scores)}")
                print(f"平均分：{sum(valid_scores) / len(valid_scores):.2f}")
            messages.success(request, f'成功保存 {len(score_records)} 条成绩记录')
            return redirect('score_processor:score_list')

        except Exception as e:
            print(f"保存成绩错误: {str(e)}")  # 调试信息
            messages.error(request, f'保存成绩时出错：{str(e)}')
            return redirect('score_processor:process_scores')

        return redirect('score_processor:upload_scores')


def process_scores(self, request):
    if request.method == 'POST':
        upload_id = request.session.get('upload_id')
        if not upload_id:
            messages.error(request, "找不到上传记录")
            return redirect('score_processor:upload-scores')

        try:
            upload = ExamUpload.objects.get(id=upload_id)
            processor = ScoreProcessorService()

            # 开始处理
            upload.status = 'PROCESSING'
            upload.save()

            result = processor.process_scores(processor.df, upload_id)

            if result['success']:
                # 保存处理结果
                processor.save_results(result['results'])

                # 更新状态
                upload.status = 'COMPLETED'
                upload.save()

                messages.success(request, "成绩处理成功")
                request.session.pop('upload_id', None)
                return redirect('score_analysis:score_processor_scorestudentbasic_changelist')
            else:
                upload.status = 'FAILED'
                upload.error_message = result['error']
                upload.save()
                messages.error(request, f"处理失败: {result['error']}")

        except Exception as e:
            upload.status = 'FAILED'
            upload.error_message = str(e)
            upload.save()
            messages.error(request, f"处理失败: {str(e)}")

    return redirect('score_processor:preview_scores')