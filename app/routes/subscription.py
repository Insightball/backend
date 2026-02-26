from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import stripe
import os
from datetime import datetime, timedelta

from app.database import get_db
from app.models import User, Club
from app.dependencies import get_current_active_user
from pydantic import BaseModel

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

STRIPE_PRICE_COACH = os.getenv("STRIPE_PRICE_COACH", "price_coach_29")
STRIPE_PRICE_CLUB  = os.getenv("STRIPE_PRICE_CLUB",  "price_club_99")

class CheckoutSessionCreate(BaseModel):
    plan: str
    success_url: str
    cancel_url: str

class PortalSessionCreate(BaseModel):
    return_url: str

# ─────────────────────────────────────────────
# CHECKOUT — Trial 7 jours avec CB requise
# ─────────────────────────────────────────────
@router.post("/create-checkout-session")
async def create_checkout_session(
    data: CheckoutSessionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        if data.plan == "coach":
            price_id = STRIPE_PRICE_COACH
        elif data.plan == "club":
            price_id = STRIPE_PRICE_CLUB
        else:
            raise HTTPException(status_code=400, detail="Invalid plan")

        # Créer ou récupérer le customer Stripe
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={"user_id": current_user.id, "name": current_user.name}
            )
            current_user.stripe_customer_id = customer.id
            db.commit()

        # Checkout avec trial 7 jours — CB requise mais pas prélevée
        checkout_session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            subscription_data={
                'trial_period_days': 7,
                'metadata': {'user_id': current_user.id, 'plan': data.plan}
            },
            success_url=data.success_url + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=data.cancel_url,
            metadata={'user_id': current_user.id, 'plan': data.plan}
        )

        return {"session_id": checkout_session.id, "url": checkout_session.url}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────
# TRIAL STATUS — frontend sait où en est l'user
# ─────────────────────────────────────────────
@router.get("/trial-status")
async def get_trial_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Retourne l'état du trial et de l'abonnement.
    Le frontend utilise ça pour :
    - Afficher le bandeau "X jours restants"
    - Flouter le dashboard si trial expiré sans abo
    """
    now = datetime.utcnow()

    # Abonnement actif → accès total
    if current_user.stripe_subscription_id:
        try:
            sub = stripe.Subscription.retrieve(current_user.stripe_subscription_id)
            sub_dict = sub.to_dict() if hasattr(sub, 'to_dict') else dict(sub)
            if sub_dict.get('status') in ('active', 'trialing'):
                return {
                    "access": "full",
                    "status": sub_dict.get('status'),
                    "trial_active": sub_dict.get('status') == 'trialing',
                    "trial_ends_at": sub_dict.get('trial_end'),
                    "match_used": getattr(current_user, 'trial_match_used', False),
                    "plan": current_user.plan.value if hasattr(current_user.plan, 'value') else current_user.plan,
                }
        except stripe.error.StripeError:
            pass

    # Pas d'abo Stripe → vérifier trial local (7 jours depuis inscription)
    trial_ends_at = getattr(current_user, 'trial_ends_at', None)
    if trial_ends_at is None:
        # Fallback : 7 jours depuis created_at
        trial_ends_at = current_user.created_at + timedelta(days=7)

    trial_active = now < trial_ends_at
    days_left = max(0, (trial_ends_at - now).days)
    match_used = getattr(current_user, 'trial_match_used', False)

    if trial_active:
        return {
            "access": "trial",
            "trial_active": True,
            "days_left": days_left,
            "trial_ends_at": trial_ends_at.isoformat(),
            "match_used": match_used,
            "plan": None,
        }
    else:
        return {
            "access": "expired",
            "trial_active": False,
            "days_left": 0,
            "match_used": match_used,
            "plan": None,
        }


# ─────────────────────────────────────────────
# PORTAL CLIENT
# ─────────────────────────────────────────────
@router.post("/create-portal-session")
async def create_portal_session(
    data: PortalSessionCreate,
    current_user: User = Depends(get_current_active_user)
):
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No active subscription")
    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=data.return_url,
        )
        return {"url": portal_session.url}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────
# SUBSCRIPTION STATUS (paramètres / dashboard)
# ─────────────────────────────────────────────
@router.get("/subscription-status")
async def get_subscription_status(
    current_user: User = Depends(get_current_active_user)
):
    if not current_user.stripe_subscription_id:
        if current_user.stripe_customer_id:
            try:
                subs = stripe.Subscription.list(
                    customer=current_user.stripe_customer_id,
                    status='active',
                    limit=1
                )
                if subs.data:
                    sub = subs.data[0]
                    return {
                        "active": True,
                        "plan": current_user.plan.value if hasattr(current_user.plan, 'value') else current_user.plan,
                        "status": sub.status,
                        "current_period_end": sub.current_period_end,
                        "cancel_at_period_end": sub.cancel_at_period_end,
                    }
            except stripe.error.StripeError:
                pass
        return {
            "active": False,
            "plan": current_user.plan.value if hasattr(current_user.plan, 'value') else current_user.plan,
            "status": "inactive"
        }

    try:
        subscription = stripe.Subscription.retrieve(current_user.stripe_subscription_id)
        plan_val = current_user.plan.value if hasattr(current_user.plan, 'value') else current_user.plan
        sub_dict = subscription.to_dict() if hasattr(subscription, 'to_dict') else dict(subscription)
        period_end = None
        try:
            items_data = sub_dict.get('items', {}).get('data', [])
            if items_data:
                period_end = items_data[0].get('current_period_end')
        except Exception:
            pass
        if not period_end:
            period_end = sub_dict.get('current_period_end')
        return {
            "active": sub_dict.get('status') in ('active', 'trialing'),
            "plan": plan_val,
            "status": sub_dict.get('status'),
            "current_period_end": period_end,
            "cancel_at_period_end": sub_dict.get('cancel_at_period_end', False),
        }
    except stripe.error.StripeError as e:
        return {
            "active": False,
            "plan": current_user.plan.value if hasattr(current_user.plan, 'value') else current_user.plan,
            "status": "error",
            "error": str(e)
        }


# ─────────────────────────────────────────────
# WEBHOOKS STRIPE
# ─────────────────────────────────────────────
@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload    = await request.body()
    sig_header = request.headers.get('stripe-signature')
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # ── Checkout complété (CB enregistrée, trial démarré)
    if event['type'] == 'checkout.session.completed':
        session  = event['data']['object']
        user_id  = session['metadata'].get('user_id')
        plan_str = session['metadata'].get('plan', '').upper()

        user = db.query(User).filter(User.id == user_id).first()
        if user:
            from app.models.user import PlanType
            try:
                user.plan = PlanType(plan_str)
            except ValueError:
                user.plan = PlanType.COACH
            user.stripe_subscription_id = session.get('subscription')
            user.stripe_customer_id     = session.get('customer') or user.stripe_customer_id
            user.is_active = True
            db.commit()

    # ── Trial démarré
    elif event['type'] == 'customer.subscription.trial_will_end':
        # J-3 avant fin trial — Stripe envoie cet event
        # TODO : envoyer email de rappel via Brevo
        pass

    # ── Abonnement actif après trial (premier prélèvement réussi)
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        if invoice.get('billing_reason') == 'subscription_cycle':
            user = db.query(User).filter(
                User.stripe_customer_id == invoice['customer']
            ).first()
            if user:
                user.is_active = True
                db.commit()

    # ── Paiement échoué après trial
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        user = db.query(User).filter(
            User.stripe_customer_id == invoice['customer']
        ).first()
        if user:
            user.is_active = False
            db.commit()

    # ── Abonnement annulé
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        user = db.query(User).filter(
            User.stripe_customer_id == subscription['customer']
        ).first()
        if user:
            user.is_active = False
            user.stripe_subscription_id = None
            db.commit()

    # ── Abonnement mis à jour
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        user = db.query(User).filter(
            User.stripe_customer_id == subscription['customer']
        ).first()
        if user:
            user.is_active = subscription['status'] in ('active', 'trialing')
            db.commit()

    return {"status": "success"}


# ─────────────────────────────────────────────
# ANNULATION
# ─────────────────────────────────────────────
@router.post("/cancel-subscription")
async def cancel_subscription(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if not current_user.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription")
    try:
        subscription = stripe.Subscription.modify(
            current_user.stripe_subscription_id,
            cancel_at_period_end=True
        )
        return {"success": True, "cancel_at": subscription.cancel_at}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
