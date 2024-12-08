from django.db import connection


class RankingService:
    @staticmethod
    def generate_rankings(exam_id=None):
        """生成排名数据"""

        # 1. 基础SQL - 创建临时科目表
        subjects_sql = """
        WITH RECURSIVE subjects AS (
            SELECT 'total' as subject_id, 'total_score' as score_column
            UNION ALL SELECT 'chinese', 'chinese'
            UNION ALL SELECT 'math', 'math'
            UNION ALL SELECT 'english', 'english'
            UNION ALL SELECT 'physics', 'physics'
            UNION ALL SELECT 'chemistry', 'chemistry'
            UNION ALL SELECT 'biology', 'biology'
            UNION ALL SELECT 'history', 'history'
            UNION ALL SELECT 'politics', 'politics'
            UNION ALL SELECT 'geography', 'geography'
        )
        """

        # 2. 主要排名SQL
        rankings_sql = """
        INSERT INTO score_rankings 
            (exam_id, unified_student_id, subject_id, stream_type, level_type, 
             raw_score, raw_score_rank, total_count, percentile, create_time)
        WITH rankings AS (
            SELECT 
                s.exam_id,
                s.student_id as unified_student_id,
                sub.subject_id,
                s.select_type as stream_type,
                'city' as level_type,
                CASE sub.subject_id
                    WHEN 'total' THEN s.total_score
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
                    PARTITION BY s.exam_id, sub.subject_id, s.select_type
                    ORDER BY 
                        CASE sub.subject_id
                            WHEN 'total' THEN s.total_score
                            WHEN 'chinese' THEN s.chinese
                            WHEN 'math' THEN s.math
                            WHEN 'english' THEN s.english
                            WHEN 'physics' THEN s.physics
                            WHEN 'chemistry' THEN s.chemistry
                            WHEN 'biology' THEN s.biology
                            WHEN 'history' THEN s.history
                            WHEN 'politics' THEN s.politics
                            WHEN 'geography' THEN s.geography
                        END DESC
                ) as raw_score_rank,
                COUNT(*) OVER (
                    PARTITION BY s.exam_id, sub.subject_id, s.select_type
                ) as total_count,
                ROUND(
                    (1 - (RANK() OVER (
                        PARTITION BY s.exam_id, sub.subject_id, s.select_type
                        ORDER BY 
                            CASE sub.subject_id
                                WHEN 'total' THEN s.total_score
                                WHEN 'chinese' THEN s.chinese
                                WHEN 'math' THEN s.math
                                WHEN 'english' THEN s.english
                                WHEN 'physics' THEN s.physics
                                WHEN 'chemistry' THEN s.chemistry
                                WHEN 'biology' THEN s.biology
                                WHEN 'history' THEN s.history
                                WHEN 'politics' THEN s.politics
                                WHEN 'geography' THEN s.geography
                            END DESC
                    ) - 1.0) / NULLIF(COUNT(*) OVER (
                        PARTITION BY s.exam_id, sub.subject_id, s.select_type
                    ) - 1, 0)) * 100,
                    2
                ) as percentile
            FROM score_student_basic s
            CROSS JOIN subjects sub
            WHERE 
                CASE sub.subject_id
                    WHEN 'total' THEN s.total_score IS NOT NULL
                    WHEN 'chinese' THEN s.chinese IS NOT NULL
                    WHEN 'math' THEN s.math IS NOT NULL
                    WHEN 'english' THEN s.english IS NOT NULL
                    WHEN 'physics' THEN s.physics IS NOT NULL
                    WHEN 'chemistry' THEN s.chemistry IS NOT NULL
                    WHEN 'biology' THEN s.biology IS NOT NULL
                    WHEN 'history' THEN s.history IS NOT NULL
                    WHEN 'politics' THEN s.politics IS NOT NULL
                    WHEN 'geography' THEN s.geography IS NOT NULL
                END
                {exam_condition}
        )
        SELECT 
            exam_id,
            unified_student_id,
            subject_id,
            stream_type,
            level_type,
            raw_score,
            raw_score_rank,
            total_count,
            percentile,
            NOW() as create_time
        FROM rankings;
        """

        # 3. 更新阈值标记SQL - 使用实际分数线
        update_flags_sql = """
              WITH line_flags AS (
                  SELECT 
                      sr.exam_id,
                      sr.unified_student_id,
                      sr.raw_score,
                      (
                          -- 使用位运算累加各个分数线的标记
                          CASE WHEN sr.raw_score >= MAX(CASE WHEN el.line_type = 'C9层' THEN el.score END) THEN 16 ELSE 0 END +
                          CASE WHEN sr.raw_score >= MAX(CASE WHEN el.line_type = '985层' THEN el.score END) THEN 8 ELSE 0 END +
                          CASE WHEN sr.raw_score >= MAX(CASE WHEN el.line_type = '211层' THEN el.score END) THEN 4 ELSE 0 END +
                          CASE WHEN sr.raw_score >= MAX(CASE WHEN el.line_type = '双一流层' THEN el.score END) THEN 2 ELSE 0 END +
                          CASE WHEN sr.raw_score >= MAX(CASE WHEN el.line_type = '本科层' THEN el.score END) THEN 1 ELSE 0 END
                      ) as flags
                  FROM score_rankings sr
                  JOIN exam_score_lines el ON 
                      sr.exam_id = el.exam_id AND 
                      CASE 
                          WHEN sr.stream_type = 'arts' THEN '文科'
                          WHEN sr.stream_type = 'science' THEN '理科'
                          ELSE sr.stream_type 
                      END = el.stream_type
                  WHERE sr.subject_id = 'total'
                  {exam_condition}
                  GROUP BY sr.exam_id, sr.unified_student_id, sr.raw_score
              )
              UPDATE score_rankings sr
              SET total_score_threshold_flags = lf.flags
              FROM line_flags lf
              WHERE sr.exam_id = lf.exam_id 
              AND sr.unified_student_id = lf.unified_student_id
              AND sr.subject_id = 'total';
              """

        try:
            with connection.cursor() as cursor:
                # 准备exam_id条件
                exam_condition = f"AND sr.exam_id = '{exam_id}'" if exam_id else ""

                # 清除旧数据
                if exam_id:
                    cursor.execute("DELETE FROM score_rankings WHERE exam_id = %s", [exam_id])
                else:
                    cursor.execute("DELETE FROM score_rankings")

                # 执行排名计算
                full_sql = f"{subjects_sql} {rankings_sql.format(exam_condition=exam_condition)}"
                cursor.execute(full_sql)

                # 更新阈值标记
                cursor.execute(update_flags_sql.format(exam_condition=exam_condition))

                return True

        except Exception as e:
            print(f"Error generating rankings: {str(e)}")
            return False