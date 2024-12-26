# score_analysis/services/region/progress.py

from typing import List, Dict, Any
from django.db import transaction
from django.db.models import Avg, Max, Min
from collections import defaultdict

from score_processor.models import ScoreStudentBasic
from score_analysis.models import RegionCharacteristics


class RegionProgressService:
    """区域进步分析服务"""

    def __init__(self):
        self.subjects = ['总分', '语文', '数学', '英语', '物理', '化学', '生物', '历史', '政治', '地理']

    def analyze_progress(self, current_exam_id: str, district_name: str,
                         select_type: str) -> Dict:
        """
        分析区域进步情况
        Args:
            current_exam_id: 当前考试ID
            district_name: 区县名称
            select_type: 文理科类型
        Returns:
            Dict: 进步分析数据
        """
        try:
            # 1. 获取当前考试的特征数据
            current_characteristics = RegionCharacteristics.objects.get(
                exam_id=current_exam_id,
                district_name=district_name,
                select_type=select_type
            )

            # 2. 获取上次考试ID
            previous_exam = ScoreStudentBasic.objects.filter(
                exam_id__lt=current_exam_id,
                district_name=district_name,
                select_type=select_type
            ).values('exam_id').distinct().order_by('-exam_id').first()

            if not previous_exam:
                return {}

            # 3. 获取上次考试的特征数据
            previous_characteristics = RegionCharacteristics.objects.get(
                exam_id=previous_exam['exam_id'],
                district_name=district_name,
                select_type=select_type
            )

            # 4. 计算进步指标
            progress_data = self._calculate_progress(
                current_characteristics,
                previous_characteristics
            )

            return progress_data

        except RegionCharacteristics.DoesNotExist:
            print("Characteristics data not found")
            return {}
        except Exception as e:
            print(f"Error in analyze_progress: {str(e)}")
            return {}

    def _calculate_progress(self, current: RegionCharacteristics,
                            previous: RegionCharacteristics) -> Dict:
        """计算进步指标"""
        progress = {}

        # 1. 对比各科目特征
        current_features = current.subject_features
        previous_features = previous.subject_features

        for subject_data in current_features.get('all_subjects', []):
            subject = subject_data['subject']
            # 找到上次考试中对应科目的数据
            prev_subject_data = next(
                (s for s in previous_features.get('all_subjects', [])
                 if s['subject'] == subject),
                None
            )

            if prev_subject_data:
                progress[subject] = {
                    # T分变化
                    't_score_change': round(
                        subject_data['t_score'] - prev_subject_data['t_score'],
                        2
                    ),
                    # 平均分变化
                    'mean_change': round(
                        subject_data['mean'] - prev_subject_data['mean'],
                        2
                    ),
                    # 优秀率变化
                    'excellent_rate_change': round(
                        subject_data['excellent_rate'] - prev_subject_data['excellent_rate'],
                        2
                    ),
                    # 合格率变化
                    'pass_rate_change': round(
                        subject_data['pass_rate'] - prev_subject_data['pass_rate'],
                        2
                    ),
                    # 当前数据
                    'current': subject_data,
                    # 上次数据
                    'previous': prev_subject_data
                }

        # 2. 分析强弱势学科变化
        strong_subjects_change = self._analyze_strong_subjects_change(
            current_features.get('strong_subjects', []),
            previous_features.get('strong_subjects', [])
        )

        weak_subjects_change = self._analyze_weak_subjects_change(
            current_features.get('weak_subjects', []),
            previous_features.get('weak_subjects', [])
        )

        # 3. 生成进步分析总结
        summary = self._generate_progress_summary(
            progress,
            strong_subjects_change,
            weak_subjects_change
        )

        return {
            'progress_data': progress,
            'strong_subjects_change': strong_subjects_change,
            'weak_subjects_change': weak_subjects_change,
            'summary': summary
        }

    def _analyze_strong_subjects_change(self, current_strong: List,
                                        previous_strong: List) -> Dict:
        """分析强势学科变化"""
        current_subjects = {s['subject'] for s in current_strong}
        previous_subjects = {s['subject'] for s in previous_strong}

        return {
            'maintained': list(current_subjects & previous_subjects),  # 保持强势
            'new': list(current_subjects - previous_subjects),  # 新增强势
            'lost': list(previous_subjects - current_subjects)  # 失去强势
        }

    def _analyze_weak_subjects_change(self, current_weak: List,
                                      previous_weak: List) -> Dict:
        """分析弱势学科变化"""
        current_subjects = {s['subject'] for s in current_weak}
        previous_subjects = {s['subject'] for s in previous_weak}

        return {
            'maintained': list(current_subjects & previous_subjects),  # 持续弱势
            'new': list(current_subjects - previous_subjects),  # 新增弱势
            'improved': list(previous_subjects - current_subjects)  # 改善弱势
        }

    def _generate_progress_summary(self, progress_data: Dict,
                                   strong_change: Dict,
                                   weak_change: Dict) -> Dict:
        """生成进步情况总结"""
        # 1. 找出进步和退步最明显的科目
        subject_changes = [
            {
                'subject': subject,
                'change': data['t_score_change'],
                'excellent_rate_change': data['excellent_rate_change'],
                'pass_rate_change': data['pass_rate_change']
            }
            for subject, data in progress_data.items()
        ]

        improved = sorted(
            [s for s in subject_changes if s['change'] > 0],
            key=lambda x: x['change'],
            reverse=True
        )[:3]

        declined = sorted(
            [s for s in subject_changes if s['change'] < 0],
            key=lambda x: x['change']
        )[:3]

        # 2. 分析整体趋势
        overall_trend = 'up' if len(improved) > len(declined) else 'down'

        # 3. 强弱势变化分析
        strength_changes = {
            'improved': len(weak_change['improved']),  # 改善的弱势学科数
            'weakened': len(strong_change['lost'])  # 失去的强势学科数
        }

        return {
            'most_improved': improved,
            'most_declined': declined,
            'overall_trend': overall_trend,
            'strength_changes': strength_changes,
            'highlights': {
                'new_strong': strong_change['new'],
                'improved_weak': weak_change['improved']
            },
            'concerns': {
                'new_weak': weak_change['new'],
                'lost_strong': strong_change['lost']
            }
        }