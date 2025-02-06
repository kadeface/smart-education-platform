# score_analysis/services/growth_model_service.py
from django.db import connection
import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
import warnings

warnings.filterwarnings('ignore')


class GrowthModelService:
    """学习曲线增长模型服务类"""

    def __init__(self):
        self.subjects = ['chinese', 'math', 'english', 'physics',
                         'chemistry', 'biology', 'history',
                         'politics', 'geography']

    def _linear_model(self, t, beta0, beta1):
        """线性增长模型"""
        return beta0 + beta1 * t

    def _quadratic_model(self, t, beta0, beta1, beta2):
        """二次曲线模型"""
        return beta0 + beta1 * t + beta2 * t ** 2

    def _piecewise_linear(self, t, beta0, beta1, beta2, c):
        """分段线性模型"""
        return beta0 + beta1 * t * (t <= c) + beta2 * t * (t > c)

    def _logistic_model(self, t, alpha, k, t0):
        """Logistic增长模型"""
        return alpha / (1 + np.exp(-k * (t - t0)))

    def fit_models(self, times, scores):
        """
        拟合所有模型并选择最佳拟合模型

        Args:
            times: 时间序列
            scores: 成绩序列

        Returns:
            dict: 包含最佳模型信息的字典
        """
        models = {}

        # 1. 线性模型
        try:
            linear_params, _ = curve_fit(self._linear_model, times, scores)
            linear_pred = self._linear_model(times, *linear_params)
            linear_r2 = r2_score(scores, linear_pred)
            models['linear'] = {
                'name': '线性增长',
                'params': linear_params,
                'r2': linear_r2,
                'predictions': linear_pred
            }
        except:
            pass

        # 2. 二次曲线
        try:
            quad_params, _ = curve_fit(self._quadratic_model, times, scores)
            quad_pred = self._quadratic_model(times, *quad_params)
            quad_r2 = r2_score(scores, quad_pred)
            models['quadratic'] = {
                'name': '增速变化',
                'params': quad_params,
                'r2': quad_r2,
                'predictions': quad_pred
            }
        except:
            pass

        # 3. 分段线性（尝试不同的转折点）
        best_piecewise_r2 = -np.inf
        for c in times[1:-1]:  # 尝试每个中间时间点作为转折点
            try:
                piecewise_params, _ = curve_fit(
                    lambda t, b0, b1, b2: self._piecewise_linear(t, b0, b1, b2, c),
                    times, scores
                )
                piecewise_pred = self._piecewise_linear(
                    times, *piecewise_params, c
                )
                piecewise_r2 = r2_score(scores, piecewise_pred)

                if piecewise_r2 > best_piecewise_r2:
                    best_piecewise_r2 = piecewise_r2
                    models['piecewise'] = {
                        'name': '关键转折点',
                        'params': (*piecewise_params, c),
                        'r2': piecewise_r2,
                        'predictions': piecewise_pred
                    }
            except:
                continue

        # 4. Logistic模型
        try:
            # 估计初始参数
            alpha_init = max(scores)  # 渐近线
            k_init = 1.0  # 增长率
            t0_init = np.median(times)  # 中点

            logistic_params, _ = curve_fit(
                self._logistic_model,
                times,
                scores,
                p0=[alpha_init, k_init, t0_init]
            )
            logistic_pred = self._logistic_model(times, *logistic_params)
            logistic_r2 = r2_score(scores, logistic_pred)
            models['logistic'] = {
                'name': '饱和增长',
                'params': logistic_params,
                'r2': logistic_r2,
                'predictions': logistic_pred
            }
        except:
            pass

        # 选择最佳模型
        best_model = max(models.items(), key=lambda x: x[1]['r2'])
        return {
            'model_type': best_model[0],
            'model_name': best_model[1]['name'],
            'r2': best_model[1]['r2'],
            'params': best_model[1]['params'],
            'predictions': best_model[1]['predictions']
        }

    def analyze_student_growth(self, exam_ids, scores_df):
        """
        分析学生增长模式

        Args:
            exam_ids: 考试ID列表
            scores_df: 包含学生成绩的DataFrame

        Returns:
            dict: 分析结果
        """
        times = np.arange(len(exam_ids))
        results = []

        for student_id in scores_df['student_id'].unique():
            student_data = scores_df[scores_df['student_id'] == student_id]

            if len(student_data) < 3:  # 至少需要3次考试记录
                continue

            student_info = {
                'student_id': student_id,
                'student_name': student_data['student_name'].iloc[0],
                'school_name': student_data['school_name'].iloc[0],
                'select_type': student_data['select_type'].iloc[0]
            }

            # 分析各科目
            for subject in self.subjects:
                scores = student_data[subject].astype(float)
                if scores.isna().any():
                    continue

                try:
                    # 拟合模型
                    model_result = self.fit_models(times, scores.values)

                    growth_info = student_info.copy()
                    growth_info.update({
                        'subject': subject,
                        'model_type': model_result['model_type'],
                        'model_name': model_result['model_name'],
                        'r2_score': model_result['r2'],
                        'params': model_result['params'],
                        'score_mean': scores.mean(),
                        'score_std': scores.std(),
                        'growth_pattern': self._classify_growth_pattern(
                            model_result['model_type'],
                            model_result['params']
                        )
                    })

                    results.append(growth_info)

                except Exception as e:
                    print(f"Error analyzing growth for student {student_id} in {subject}: {str(e)}")
                    continue

        return pd.DataFrame(results)

    def _classify_growth_pattern(self, model_type, params):
        """
        根据模型类型和参数分类增长模式
        """
        if model_type == 'linear':
            beta1 = params[1]
            if beta1 > 0.5:
                return '稳定快速提升'
            elif beta1 > 0:
                return '稳定缓慢提升'
            else:
                return '需要关注'

        elif model_type == 'quadratic':
            beta2 = params[2]
            if beta2 > 0:
                return '加速提升'
            else:
                return '减速提升'

        elif model_type == 'piecewise':
            beta1, beta2 = params[1:3]
            if beta1 > beta2:
                return '前期快速后期放缓'
            else:
                return '前期缓慢后期加快'

        elif model_type == 'logistic':
            k = params[1]
            if k > 1:
                return '快速趋近目标'
            else:
                return '缓慢趋近目标'

        return '未知模式'