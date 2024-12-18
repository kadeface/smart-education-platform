from collections import defaultdict
from datetime import datetime
from django.db import connection

class RankingService:
    def generate_rankings(self, exam_id):
        try:
            print(f"\n=== 开始生成考试ID: {exam_id} 的排名数据 ===")

            with connection.cursor() as cursor:
                # 1. 检查考试数据
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM score_student_basic 
                    WHERE exam_id = %s
                """, [exam_id])
                result = cursor.fetchone()
                if result is None or result[0] == 0:
                    print("错误：没有找到学生成绩数据")
                    return False

                student_count = result[0]
                print(f"找到 {student_count} 条学生成绩记录")

                # 2. 清除旧数据
                cursor.execute("""
                    DELETE FROM score_rankings 
                    WHERE exam_id = %s
                """, [exam_id])
                print(f"已清除 {cursor.rowcount} 条旧数据")

                # 3. 生成排名数据
                cursor.execute("""
                    REPLACE INTO score_rankings (
                        exam_id, 
                        unified_student_id, 
                        student_name,
                        school_name,
                        subject_id, 
                        select_type, 
                        level_type,
                        raw_score, 
                        raw_score_rank, 
                        total_count, 
                        percentile, 
                        create_time
                    )
                    WITH RECURSIVE subjects AS (
                        SELECT 'total_score' as subject_id, 'total_score' as score_column
                        UNION ALL SELECT 'chinese', 'chinese'
                        UNION ALL SELECT 'math', 'math'
                        UNION ALL SELECT 'english', 'english'
                        UNION ALL SELECT 'physics', 'physics'
                        UNION ALL SELECT 'chemistry', 'chemistry'
                        UNION ALL SELECT 'biology', 'biology'
                        UNION ALL SELECT 'history', 'history'
                        UNION ALL SELECT 'politics', 'politics'
                        UNION ALL SELECT 'geography', 'geography'
                    ),
                    rankings AS (
                        SELECT
                            s.exam_id,
                            s.student_id as unified_student_id,
                            s.student_name,
                            s.school_name,
                            sub.subject_id,
                            s.select_type,
                            s.district_name as level_type,  -- 直接使用区县名作为层级
                            CASE sub.subject_id
                                WHEN 'total_score' THEN s.total_score
                                WHEN 'chinese' THEN s.chinese
                                WHEN 'math' THEN s.math
                                WHEN 'english' THEN s.english
                                WHEN 'physics' THEN s.physics
                                WHEN 'chemistry' THEN s.chemistry
                                WHEN 'biology' THEN s.biology
                                WHEN 'history' THEN s.history
                                WHEN 'politics' THEN s.politics
                                WHEN 'geography' THEN s.geography
                            END as raw_score,
                            RANK() OVER (
                                PARTITION BY s.exam_id, sub.subject_id, s.select_type, s.district_name
                                ORDER BY
                                    CASE sub.subject_id
                                        WHEN 'total_score' THEN s.total_score
                                        WHEN 'chinese' THEN s.chinese
                                        WHEN 'math' THEN s.math
                                        WHEN 'english' THEN s.english
                                        WHEN 'physics' THEN s.physics
                                        WHEN 'chemistry' THEN s.chemistry
                                        WHEN 'biology' THEN s.biology
                                        WHEN 'history' THEN s.history
                                        WHEN 'politics' THEN s.politics
                                        WHEN 'geography' THEN s.geography
                                    END DESC,
                                    CASE 
                                        WHEN sub.subject_id = 'total_score' THEN s.math 
                                        ELSE NULL 
                                    END DESC,
                                    CASE 
                                        WHEN sub.subject_id = 'total_score' THEN s.chinese 
                                        ELSE NULL 
                                    END DESC
                            ) as raw_score_rank,
                            COUNT(*) OVER (
                                PARTITION BY s.exam_id, sub.subject_id, s.select_type, s.district_name
                            ) as total_count,
                            ROUND(
                                (1 - (RANK() OVER (
                                    PARTITION BY s.exam_id, sub.subject_id, s.select_type, s.district_name
                                    ORDER BY
                                        CASE sub.subject_id
                                            WHEN 'total_score' THEN s.total_score
                                            WHEN 'chinese' THEN s.chinese
                                            WHEN 'math' THEN s.math
                                            WHEN 'english' THEN s.english
                                            WHEN 'physics' THEN s.physics
                                            WHEN 'chemistry' THEN s.chemistry
                                            WHEN 'biology' THEN s.biology
                                            WHEN 'history' THEN s.history
                                            WHEN 'politics' THEN s.politics
                                            WHEN 'geography' THEN s.geography
                                        END DESC,
                                        CASE 
                                            WHEN sub.subject_id = 'total_score' THEN s.math 
                                            ELSE NULL 
                                        END DESC,
                                        CASE 
                                            WHEN sub.subject_id = 'total_score' THEN s.chinese 
                                            ELSE NULL 
                                        END DESC
                                ) - 1.0) / NULLIF(COUNT(*) OVER (
                                    PARTITION BY s.exam_id, sub.subject_id, s.select_type, s.district_name
                                ) - 1, 0)) * 100,
                                2
                            ) as percentile,
                            NOW() as create_time
                        FROM score_student_basic s
                        CROSS JOIN subjects sub
                        WHERE s.exam_id = %s
                        AND CASE sub.subject_id
                            WHEN 'total_score' THEN s.total_score > 0
                            WHEN 'chinese' THEN s.chinese > 0
                            WHEN 'math' THEN s.math > 0
                            WHEN 'english' THEN s.english > 0
                            WHEN 'physics' THEN s.physics > 0
                            WHEN 'chemistry' THEN s.chemistry > 0
                            WHEN 'biology' THEN s.biology > 0
                            WHEN 'history' THEN s.history > 0
                            WHEN 'politics' THEN s.politics > 0
                            WHEN 'geography' THEN s.geography > 0
                        END
                    )
                    SELECT * FROM rankings;
                """, [exam_id])

                print(f"已插入 {cursor.rowcount} 条排名记录")
                connection.commit()
                print("\n=== 排名数据生成完成！===")
                return True

        except Exception as e:
            print(f"\n=== 生成排名时发生错误 ===")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            connection.rollback()
            raise