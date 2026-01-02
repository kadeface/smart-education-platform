from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from score_analysis.services.ranking_service import RankingService
from score_analysis.database.database import get_db

router = APIRouter()

@router.get("/teacher/evaluation/{teacher_id}")
async def get_teacher_evaluation(
    teacher_id: str,
    semester: str,
    db: Session = Depends(get_db)
):
    """
    获取教师评价数据
    """
    ranking_service = RankingService(db)
    return ranking_service.calculate_teacher_evaluation_score(teacher_id, semester)

@router.get("/class/evaluation/{class_id}")
async def get_class_evaluation(
    class_id: str,
    semester: str,
    db: Session = Depends(get_db)
):
    """
    获取班级评价数据
    """
    ranking_service = RankingService(db)
    return ranking_service.calculate_class_evaluation_score(class_id, semester) 