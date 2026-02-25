from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import stripe
import os
from datetime import datetime

from app.database import get_db
from app.models import User, Club
from app.dependencies import get_current_active_user
from pydantic import BaseModel

router = APIRouter()

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Price IDs from Stripe Dashboard
STRIPE_PRICE_COACH = os.getenv("STRIPE_PRICE_COACH", "price_coach_29")
STRIPE_PRICE_CLUB = os.getenv("STRIPE_PRICE_CLUB", "price_club_89")

class CheckoutSessionCreate(BaseModel):
    plan: str  # "coach" or "club"
    success_url: str
    cancel_url: str

class PortalSessionCreate(BaseModel):
    return_url: str

@router.post("/create-checkout-session")
async def create_checkout_session(
    data: CheckoutSessionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create Stripe checkout session for subscription"""
    
    try:
        # Determine price based on plan
        if data.plan == "coach":
            price_id = STRIPE_PRICE_COACH
        elif data.plan == "club":
            price_id = STRIPE_PRICE_CLUB
        else:
            raise HTTPException(status_code=400, detail="Invalid plan")
        
        # Create or get Stripe customer
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={
                    "user_id": current_user.id,
                    "name": current_user.name
                }
            )
            current_user.stripe_customer_id = customer.id
            db.commit()
        
        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=data.success_url + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=data.cancel_url,
            metadata={
                'user_id': current_user.id,
                'plan': data.plan
            }
        )
        
        return {"session_id": checkout_session.id, "url": checkout_session.url}
        
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/create-portal-session")
async def create_portal_session(
    data: PortalSessionCreate,
    current_user: User = Depends(get_current_active_user)
):
    """Create Stripe customer portal session"""
    
    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No active subscription"
        )
    
    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=data.return_url,
        )
        
        return {"url": portal_session.url}
        
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/subscription-status")
async def get_subscription_status(
    current_user: User = Depends(get_current_active_user)
):
    """Get current subscription status"""
    
    if not current_user.stripe_subscription_id:
        return {
            "active": False,
            "plan": current_user.plan,
            "status": "inactive"
        }
    
    try:
        subscription = stripe.Subscription.retrieve(current_user.stripe_subscription_id)
        
        return {
            "active": subscription.status == "active",
            "plan": current_user.plan,
            "status": subscription.status,
            "current_period_end": subscription.current_period_end,
            "cancel_at_period_end": subscription.cancel_at_period_end
        }
        
    except stripe.error.StripeError as e:
        return {
            "active": False,
            "plan": current_user.plan,
            "status": "error",
            "error": str(e)
        }

@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe webhooks"""
    
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Handle different event types
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']

        user_id = session['metadata'].get('user_id')
        plan_str = session['metadata'].get('plan', '').upper()  # 'club' → 'CLUB'

        user = db.query(User).filter(User.id == user_id).first()
        if user:
            from app.models.user import PlanType
            try:
                user.plan = PlanType(plan_str)
            except ValueError:
                user.plan = PlanType.COACH
            user.stripe_subscription_id = session.get('subscription')
            user.stripe_customer_id = session.get('customer') or user.stripe_customer_id
            user.is_active = True
            db.commit()
    
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        
        # Find user by customer_id
        user = db.query(User).filter(
            User.stripe_customer_id == subscription['customer']
        ).first()
        
        if user:
            user.is_active = False
            user.stripe_subscription_id = None
            db.commit()
    
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        
        # Find user
        user = db.query(User).filter(
            User.stripe_customer_id == subscription['customer']
        ).first()
        
        if user:
            # Update subscription status
            if subscription['status'] == 'active':
                user.is_active = True
            else:
                user.is_active = False
            
            db.commit()
    
    return {"status": "success"}

@router.post("/cancel-subscription")
async def cancel_subscription(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cancel subscription at period end"""
    
    if not current_user.stripe_subscription_id:
        raise HTTPException(
            status_code=400,
            detail="No active subscription"
        )
    
    try:
        subscription = stripe.Subscription.modify(
            current_user.stripe_subscription_id,
            cancel_at_period_end=True
        )
        
        return {
            "success": True,
            "cancel_at": subscription.cancel_at
        }
        
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
