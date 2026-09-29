import asyncio, uuid
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import *
from app.core.security import hash_password

async def main():
    async with SessionLocal() as db:
        users=[("admin@example.local","Администратор","Admin123!",UserRole.ADMIN),("teacher@example.local","Преподаватель","Teacher123!",UserRole.TEACHER),("student@example.local","Обучающийся","Student123!",UserRole.STUDENT)]
        created={}
        for email,name,password,role in users:
            u=await db.scalar(select(User).where(User.email==email))
            if not u: u=User(email=email,full_name=name,password_hash=hash_password(password),role=role); db.add(u); await db.flush()
            created[role]=u
        demo_group=await db.scalar(select(Group).where(Group.name=="Демонстрационная группа ДДС"))
        if not demo_group:
            demo_group=Group(name="Демонстрационная группа ДДС");db.add(demo_group);await db.flush()
        if not await db.get(GroupMember,(demo_group.id,created[UserRole.STUDENT].id)):
            db.add(GroupMember(group_id=demo_group.id,user_id=created[UserRole.STUDENT].id))
        scenario_data=[
            ("DEMO-001","Учебный ДТП","ДТП",1,{"message":"Карточка 112: произошло ДТП, требуется помощь.","tags":["место","число участников","пострадавшие"]},{"services":["ДДС"],"status":"ПРИНЯТО"}),
            ("DEMO-002","Учебный БПЛА","БПЛА",2,{"message":"Карточка 112: наблюдается БПЛА.","tags":["место","направление","время"]},{"services":["ДДС"],"status":"ПРИНЯТО"}),
            ("DEMO-003","Ребёнок в опасности","Ребенок в опасности",2,{"message":"Карточка 112: ребёнок находится в потенциально опасной ситуации.","tags":["место","обстоятельства","контакт"]},{"services":["ДДС"],"status":"ПРИНЯТО"}),
        ]
        for code,title,cat,diff,payload,expected in scenario_data:
            s=await db.scalar(select(Scenario).where(Scenario.code==code))
            if not s:
                s=Scenario(code=code,title=title,category=cat,difficulty=diff,incident_payload=payload,expected_state=expected,published=True,created_by=created[UserRole.TEACHER].id); db.add(s); await db.flush()
                db.add(EventCard(scenario_id=s.id,title=title,body=payload,time_limit_sec=120))
                db.add(ExpectedAction(scenario_id=s.id,action_type="SELECT_INCIDENT",payload={"category":cat},weight=2,order_no=1))
                db.add(ExpectedAction(scenario_id=s.id,action_type="SELECT_STATUS",payload={"status":"ПРИНЯТО"},weight=2,order_no=2))
                db.add(ExpectedAction(scenario_id=s.id,action_type="TEXT_INPUT",payload={"text":"Сообщение принято, информация зафиксирована."},weight=1,order_no=3))
                db.add(ExpectedAction(scenario_id=s.id,action_type="SELECT_SERVICES",payload={"services":["ДДС"]},weight=1,order_no=4))
                db.add(ExpectedAction(scenario_id=s.id,action_type="SELECT_TAGS",payload={"tags":payload["tags"]},weight=1,order_no=5))
            elif s.incident_payload.get("message","").startswith(("Звонок заявителя", "Поступило сообщение", "Сообщение о ребёнке")):
                s.incident_payload=payload
                card=await db.scalar(select(EventCard).where(EventCard.scenario_id==s.id))
                if card: card.body=payload
        await db.commit()

if __name__=="__main__": asyncio.run(main())
