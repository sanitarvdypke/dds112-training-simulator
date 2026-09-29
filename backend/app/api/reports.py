import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.entities import AssessmentResult, UserRole
from app.api.deps import require_roles
from app.services.reports import assessment_csv, assessment_pdf
from sqlalchemy import select
from app.models.entities import CallSession, TrainingSession, User

router=APIRouter(prefix="/reports",tags=["reports"])
@router.get("/assessments")
async def list_results(db=Depends(get_db),user=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    query=select(AssessmentResult,User.full_name,TrainingSession.title).join(CallSession,CallSession.id==AssessmentResult.call_session_id).join(User,User.id==CallSession.student_id).join(TrainingSession,TrainingSession.id==CallSession.training_session_id).order_by(AssessmentResult.created_at.desc())
    if user.role==UserRole.TEACHER: query=query.where(TrainingSession.teacher_id==user.id)
    return [{"id":str(r.id),"call_session_id":str(r.call_session_id),"student":name,"session":title,"score":r.score,"max_score":r.max_score,"duration_sec":r.duration_sec,"over_time":r.over_time,"details":r.details} for r,name,title in (await db.execute(query)).all()]

@router.get("/summary")
async def progress_summary(include_qa:bool=False,db=Depends(get_db),user=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    query=select(AssessmentResult,User.id,User.full_name).join(CallSession,CallSession.id==AssessmentResult.call_session_id).join(User,User.id==CallSession.student_id).join(TrainingSession,TrainingSession.id==CallSession.training_session_id).order_by(AssessmentResult.created_at)
    if user.role==UserRole.TEACHER: query=query.where(TrainingSession.teacher_id==user.id)
    if not include_qa: query=query.where(~TrainingSession.title.ilike("QA %"),~User.full_name.ilike("QA %"))
    rows=(await db.execute(query)).all()
    grouped={}
    for result,student_id,name in rows:
        percent=round((result.score/result.max_score*100) if result.max_score else 0,1)
        item=grouped.setdefault(str(student_id),{"student_id":str(student_id),"student":name,"attempts":0,"percents":[],"durations":[],"overtime_count":0,"recent":[]})
        item["attempts"]+=1;item["percents"].append(percent);item["durations"].append(result.duration_sec);item["overtime_count"]+=int(result.over_time)
        item["recent"].append({"at":result.created_at.isoformat(),"percent":percent})
    students=[]
    for item in grouped.values():
        students.append({"student_id":item["student_id"],"student":item["student"],"attempts":item["attempts"],
            "average_percent":round(sum(item["percents"])/item["attempts"],1),"best_percent":max(item["percents"]),
            "average_duration":round(sum(item["durations"])/item["attempts"]),"overtime_count":item["overtime_count"],"recent":item["recent"][-8:]})
    students.sort(key=lambda row:(-row["average_percent"],row["student"]))
    total=len(rows)
    all_percent=[percent for item in grouped.values() for percent in item["percents"]]
    all_duration=[duration for item in grouped.values() for duration in item["durations"]]
    return {"total_results":total,"students_count":len(students),
        "average_percent":round(sum(all_percent)/total,1) if total else 0,
        "average_duration":round(sum(all_duration)/total) if total else 0,
        "overtime_count":sum(item["overtime_count"] for item in grouped.values()),"students":students}

async def accessible_result(db,result_id,user):
    query=select(AssessmentResult).join(CallSession).join(TrainingSession).where(AssessmentResult.id==result_id)
    if user.role==UserRole.TEACHER: query=query.where(TrainingSession.teacher_id==user.id)
    result=await db.scalar(query)
    if not result: raise HTTPException(404,"Результат не найден или недоступен")
    return result

@router.get("/assessment/{result_id}.csv")
async def csv_report(result_id:uuid.UUID,db=Depends(get_db),user=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    result=await accessible_result(db,result_id,user)
    if not result: raise HTTPException(404,"Результат не найден")
    return Response(assessment_csv(result),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="assessment-{result_id}.csv"'})
@router.get("/assessment/{result_id}.pdf")
async def pdf_report(result_id:uuid.UUID,db=Depends(get_db),user=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    result=await accessible_result(db,result_id,user)
    if not result: raise HTTPException(404,"Результат не найден")
    return Response(assessment_pdf(result),media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="assessment-{result_id}.pdf"'})

@router.get("/assessment/{result_id}")
async def detailed_report(result_id:uuid.UUID,db=Depends(get_db),user=Depends(require_roles(UserRole.ADMIN,UserRole.TEACHER))):
    result=await accessible_result(db,result_id,user)
    return {"id":str(result.id),"score":result.score,"max_score":result.max_score,"duration_sec":result.duration_sec,
            "over_time":result.over_time,"details":result.details,"ai_feedback":result.ai_feedback}
