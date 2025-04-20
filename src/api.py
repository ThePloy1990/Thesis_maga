from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from models import SessionLocal, User
from celery_app import send_newsletter_task

app = FastAPI(title="Admin Panel API")

def get_db():
    """Зависимость, создающая сессию БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserSchema(BaseModel):
    telegram_id: str
    name: str
    email: Optional[str] = None
    risk_tolerance: Optional[str] = None
    horizon: Optional[str] = None
    goal: Optional[str] = None

    class Config:
        orm_mode = True

class NewsletterRequest(BaseModel):
    message: str

@app.post("/users/", response_model=UserSchema)
async def create_user(user: UserSchema, db: Session = Depends(get_db)):
    """Создает нового пользователя"""
    existing = db.query(User).filter(User.telegram_id == user.telegram_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    db_user = User(
        telegram_id=user.telegram_id,
        name=user.name,
        email=user.email,
        risk_tolerance=user.risk_tolerance,
        horizon=user.horizon,
        goal=user.goal
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/users/", response_model=List[UserSchema])
async def list_users(db: Session = Depends(get_db)):
    """Возвращает список всех пользователей"""
    return db.query(User).all()

@app.get("/metrics")
async def get_metrics():
    """Возвращает метрики использования (заглушка)"""
    return {
        "dau": 0,
        "requests_per_minute": 0,
        "errors_last_hour": 0
    }

@app.post("/newsletter/")
async def newsletter(req: NewsletterRequest):
    """Запускает фоновую задачу рассылки"""
    send_newsletter_task.delay(req.message)
    return {"status": "scheduled", "message": req.message} 