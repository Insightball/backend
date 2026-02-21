from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import uuid

from app.database import get_db
from app.models import User
from app.models.notification import Notification, NotificationType
from app.dependencies import get_current_active_user
from pydantic import BaseModel

router = APIRouter()

class NotificationResponse(BaseModel):
    id: str
    type: str
    title: str
    message: str
    link: str | None
    read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

@router.get("/", response_model=List[NotificationResponse])
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user notifications"""
    
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    
    if unread_only:
        query = query.filter(Notification.read == False)
    
    notifications = query.order_by(Notification.created_at.desc()).limit(limit).all()
    
    return notifications

@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get count of unread notifications"""
    
    count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.read == False
    ).count()
    
    return {"count": count}

@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Mark notification as read"""
    
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification non trouvée"
        )
    
    notification.read = True
    db.commit()
    
    return {"success": True}

@router.patch("/mark-all-read")
async def mark_all_as_read(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Mark all notifications as read"""
    
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.read == False
    ).update({"read": True})
    
    db.commit()
    
    return {"success": True}

@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a notification"""
    
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification non trouvée"
        )
    
    db.delete(notification)
    db.commit()
    
    return {"success": True}

# Helper function to create notification (can be called from other routes)
def create_notification(
    db: Session,
    user_id: str,
    type: NotificationType,
    title: str,
    message: str,
    link: str = None
):
    """Create a new notification"""
    
    notification = Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        link=link
    )
    
    db.add(notification)
    db.commit()
    
    return notification
