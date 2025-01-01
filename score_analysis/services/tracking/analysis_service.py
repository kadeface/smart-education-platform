from django.db import connection
from typing import Dict, List, Tuple
import json

class AnalysisService:
    def generate_analysis(self, exam_id: int, student_id: int) -> Dict:
        """生成学生成绩分析"""
        with connection.cursor() as cursor:
            # 1. 获取历史成绩
            cursor.execute("""
                SELECT 
                    ssb.total_score,
                    ssb.chinese, ssb.math, ssb.english,
                    ssb.physics, ssb.chemistry, ssb.biology,
                    ssb.history, ssb.politics, ssb.geography,
                    ssb.exam_id,
                    bec.exam_date
                FROM score_student_basic ssb
                JOIN base_exam_config bec ON ssb.exam_id = bec.exam_id
                JOIN tracking_students ts ON ssb.student_id = ts.student_code
                WHERE ts.id = %s
                ORDER BY bec.exam_date
            """, [student_id])
            history_scores = cursor.fetchall()

            if not history_scores:
                raise ValueError(f"No history scores found for student {student_id}")

            # 2. 提取总分序列
            total_scores = [row[0] for row in history_scores]

            # 3. 计算分析数据
            analysis_data = {
                'stability_score': self._calculate_stability(total_scores),
                'trend_direction': self._calculate_trend(total_scores),
                'subject_strength': self._analyze_subjects(history_scores),
                'improvement_rate': self._calculate_improvement(total_scores)
            }

            # 4. 保存或更新分析结果
            cursor.execute("""
                INSERT INTO tracking_analysis 
                    (student_id, exam_id, stability_score, trend_direction, 
                     subject_strength, improvement_rate)
                VALUES 
                    (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    stability_score = VALUES(stability_score),
                    trend_direction = VALUES(trend_direction),
                    subject_strength = VALUES(subject_strength),
                    improvement_rate = VALUES(improvement_rate)
            """, [
                student_id,
                exam_id,
                analysis_data['stability_score'],
                analysis_data['trend_direction'],
                json.dumps(analysis_data['subject_strength']),
                analysis_data['improvement_rate']
            ])

            return analysis_data

    def _calculate_slope(self, x: List[float], y: List[float]) -> float:
        """计算线性回归斜率"""
        if len(x) != len(y) or len(x) < 2:
            return 0
        try:
            x_mean = sum(x) / len(x)
            y_mean = sum(y) / len(y)
            numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
            denominator = sum((xi - x_mean) ** 2 for xi in x)
            return numerator / denominator if denominator != 0 else 0
        except:
            return 0

    def _calculate_stability(self, scores: List[float]) -> float:
        """计算稳定性得分"""
        if len(scores) < 2:
            return 100.0
        try:
            mean = sum(scores) / len(scores)
            variance = sum((x - mean) ** 2 for x in scores) / len(scores)
            std_dev = variance ** 0.5
            # 转换为0-100的得分，标准差越小，得分越高
            stability = max(0, 100 - (std_dev / mean * 100))
            return round(stability, 2)
        except:
            return 0.0

    def _calculate_trend(self, scores: List[float]) -> int:
        """计算趋势方向"""
        if len(scores) < 2:
            return 0
        try:
            # 简单线性回归计算斜率
            x = list(range(len(scores)))
            slope = self._calculate_slope(x, scores)
            # 设置趋势判断阈值
            threshold = 0.1 * sum(scores) / len(scores)  # 动态阈值
            return 1 if slope > threshold else (-1 if slope < -threshold else 0)
        except:
            return 0

    def _analyze_subjects(self, history_scores: List[Tuple]) -> Dict:
        """分析学科优势"""
        subjects = {
            1: 'chinese', 2: 'math', 3: 'english',
            4: 'physics', 5: 'chemistry', 6: 'biology',
            7: 'history', 8: 'politics', 9: 'geography'
        }

        result = {}
        for idx, subject in subjects.items():
            scores = [row[idx] for row in history_scores if row[idx] is not None]
            if len(scores) >= 2:
                avg_score = sum(scores) / len(scores)
                result[subject] = {
                    'average': round(avg_score, 2),
                    'trend': self._calculate_trend(scores),
                    'stability': self._calculate_stability(scores),
                    'latest': scores[-1],
                    'improvement': scores[-1] - scores[-2] if len(scores) >= 2 else 0
                }

        # 计算学科优势排序
        sorted_subjects = sorted(
            result.items(),
            key=lambda x: (x[1]['average'], -x[1]['stability']),
            reverse=True
        )

        # 添加排名信息
        for rank, (subject, data) in enumerate(sorted_subjects, 1):
            result[subject]['rank'] = rank

        return result

    def _calculate_improvement(self, scores: List[float]) -> float:
        """计算进步率"""
        if len(scores) < 2:
            return 0.0
        try:
            # 计算相邻考试的进步次数
            improvements = [
                1 if scores[i] > scores[i - 1] else 0
                for i in range(1, len(scores))
            ]
            # 计算进步率
            improvement_rate = sum(improvements) / len(improvements) * 100
            return round(improvement_rate, 2)
        except:
            return 0.0

    def get_detailed_analysis(self, exam_id: int, student_id: int) -> Dict:
        """获取详细分析结果"""
        analysis = self.get_analysis(exam_id, student_id)
        if not analysis:
            return None

        # 添加解释性文本
        analysis['trend_explanation'] = {
            1: "成绩呈上升趋势",
            0: "成绩保持稳定",
            -1: "成绩呈下降趋势"
        }.get(analysis['trend_direction'], "无法判断趋势")

        # 添加稳定性评价
        analysis['stability_level'] = (
            "非常稳定" if analysis['stability_score'] >= 90 else
            "较为稳定" if analysis['stability_score'] >= 75 else
            "一般稳定" if analysis['stability_score'] >= 60 else
            "不够稳定" if analysis['stability_score'] >= 45 else
            "很不稳定"
        )

        return analysis