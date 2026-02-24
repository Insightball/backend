from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
import uuid

from app.database import get_db
from app.models.lead import Lead

router = APIRouter()

class WaitlistRequest(BaseModel):
    first_name: Optional[str] = None
    last_name:  Optional[str] = None
    email:      EmailStr
    club_name:  Optional[str] = None
    role:       Optional[str] = None      # Éducateur | Entraîneur | Directeur Sportif
    category:   Optional[str] = None     # U14 … Séniors
    plan:       Optional[str] = None

class ContactRequest(BaseModel):
    name:    str
    email:   EmailStr
    message: str

@router.post("/waitlist")
async def join_waitlist(data: WaitlistRequest, db: Session = Depends(get_db)):
    existing = db.query(Lead).filter(Lead.email == data.email, Lead.type == "waitlist").first()
    if existing:
        return { "status": "already_registered" }
    lead = Lead(
        id=str(uuid.uuid4()),
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        club_name=data.club_name,
        role=data.role,
        category=data.category,
        plan=data.plan,
        type="waitlist",
        created_at=datetime.utcnow(),
    )
    db.add(lead); db.commit()
    return { "status": "ok" }

@router.post("/contact")
async def contact(data: ContactRequest, db: Session = Depends(get_db)):
    lead = Lead(
        id=str(uuid.uuid4()),
        email=data.email,
        club_name=data.name,
        message=data.message,
        type="contact",
        created_at=datetime.utcnow(),
    )
    db.add(lead); db.commit()
    return { "status": "ok" }

@router.get("/list")
async def list_leads(db: Session = Depends(get_db)):
    return db.query(Lead).order_by(Lead.created_at.desc()).all()
