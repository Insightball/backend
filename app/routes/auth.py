from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
import uuid

from app.database import get_db
from app.models import User, Club, PlanType
from app.schemas import UserSignup, UserLogin, Token, UserResponse
from app.utils.auth import verify_password, get_password_hash, create_access_token
from app.dependencies import get_current_user
from app.config import settings

router = APIRouter()

@router.post("/signup", response_model=Token)
async def signup(user_data: UserSignup, db: Session = Depends(get_db)):
    """Create a new user account"""
    
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create club if CLUB plan
    club = None
    if user_data.plan == PlanType.CLUB:
        if not user_data.club_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Club name is required for CLUB plan"
            )
        
        club = Club(
            id=str(uuid.uuid4()),
            name=user_data.club_name,
            quota_matches=10
        )
        db.add(club)
        db.flush()  # Get the club.id
    
    # Create user
    user = User(
        id=str(uuid.uuid4()),
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        name=user_data.name,
        plan=user_data.plan,
        club_id=club.id if club else None
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, 
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token"""
    
    # Find user
    user = db.query(User).filter(User.email == credentials.email).first()
    
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, 
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user info"""
    
    response = UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        plan=current_user.plan.value
    )
    
    # Add club name if user is in a club
    if current_user.club:
        response.club_name = current_user.club.name
    
    return response
