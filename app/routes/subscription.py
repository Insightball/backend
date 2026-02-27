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

# ─────────────────────────────────────────────
# EMAIL HELPER — Brevo (SendinBlue)
# ─────────────────────────────────────────────
def _send_trial_reminder_email(to_email: str, name: str, debit_date: str):
    """
    Envoie l'email de rappel J-2 avant fin trial via Resend.
    Nécessite RESEND_API_KEY dans les variables d'environnement Render.
    """
    import httpx
    resend_key = os.getenv("RESEND_API_KEY")
    if not resend_key:
        print(f"[WARN] RESEND_API_KEY manquant — email non envoyé à {to_email}")
        return
    try:
        first_name = name.split()[0] if name else "Coach"
        payload = {
            "from":    "InsightBall <contact@insightball.com>",
            "to":      [to_email],
            "subject": "Votre essai InsightBall se termine dans 2 jours",
            "html": f"""
            <div style="font-family: monospace; max-width: 520px; margin: 0 auto; padding: 32px 24px; background: #faf8f4;">
              <div style="font-size: 22px; font-weight: 900; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 24px;">
                INSIGHT<span style="color: #c9a227;">BALL</span>
              </div>
              <p style="font-size: 15px; color: #2a2a26; line-height: 1.6;">Bonjour {first_name},</p>
              <p style="font-size: 14px; color: #2a2a26; line-height: 1.7;">
                Votre essai gratuit se termine dans <strong>2 jours</strong>.<br>
                Votre carte bancaire sera débitée le <strong>{debit_date}</strong> sauf résiliation avant cette date.
              </p>
              <div style="background: #fff; border: 1px solid rgba(15,15,13,0.09); border-left: 3px solid #c9a227; padding: 14px 18px; margin: 20px 0;">
                <p style="font-size: 12px; color: rgba(15,15,13,0.55); margin: 0; line-height: 1.6;">
                  Pour annuler : connectez-vous sur insightball.com → Paramètres → Gérer mon abonnement.<br>
                  Aucune question posée, résiliation en 1 clic.
                </p>
              </div>
              <a href="https://insightball.com/dashboard/settings" style="display: inline-block; padding: 12px 24px; background: #c9a227; color: #0f0f0d; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; font-weight: 700; text-decoration: none; margin-top: 8px;">
                Gérer mon abonnement →
              </a>
              <p style="font-size: 11px; color: rgba(15,15,13,0.35); margin-top: 28px; line-height: 1.6;">
                InsightBall · contact@insightball.com<br>
                Vous recevez cet email car vous avez démarré un essai InsightBall.
              </p>
            </div>
            """,
        }
        resp = httpx.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            print(f"[WARN] Resend email failed {resp.status_code}: {resp.text}")
        else:
            print(f"[INFO] Rappel trial envoyé à {to_email}")
    except Exception as e:
        print(f"[ERR] Email reminder failed: {e}")

# 26a0Fe0f  COACH: 39 20ac/mois  |  Mettre 00e0 jour dans Render > Environment Variables
STRIPE_PRICE_COACH = os.getenv("STRIPE_PRICE_COACH", "price_coach_39")
# 26a0Fe0f  CLUB : 129 20ac/mois  |  Mettre 00e0 jour dans Render > Environment Variables
STRIPE_PRICE_CLUB  = os.getenv("STRIPE_PRICE_CLUB",  "price_club_129")

class CheckoutSessionCreate(BaseModel):
    plan: str
    success_url: str
    cancel_url: str

class PortalSessionCreate(BaseModel):
    return_url: str

# ─────────────────────────────────────────────
# CB ENREGISTRÉE ? — vérifie avant upload
# ─────────────────────────────────────────────
@router.get("/has-payment-method")
async def has_payment_method(
    current_user: User = Depends(get_current_active_user),
):
    """
    Retourne si l'user a une CB enregistrée dans Stripe.
    Utilisé par UploadMatch pour bloquer l'accès si pas de CB.
    """
    if not current_user.stripe_customer_id:
        return {"has_payment_method": False}
    try:
        methods = stripe.PaymentMethod.list(
            customer=current_user.stripe_customer_id,
            type="card",
        )
        return {"has_payment_method": len(methods.data) > 0}
    except stripe.error.StripeError:
        return {"has_payment_method": False}


# ─────────────────────────────────────────────
# SETUP INTENT — Stripe Elements sans redirection
# ─────────────────────────────────────────────
@router.post("/create-setup-intent")
async def create_setup_intent(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Crée un SetupIntent Stripe pour enregistrer la CB sans débit immédiat.
    Le frontend utilise Stripe Elements avec ce client_secret.
    """
    try:
        # Créer customer si nécessaire
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={"user_id": str(current_user.id), "name": current_user.name}
            )
            current_user.stripe_customer_id = customer.id
            db.commit()

        setup_intent = stripe.SetupIntent.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=["card"],
            metadata={"user_id": str(current_user.id)},
        )
        return {
            "client_secret": setup_intent.client_secret,
            "customer_id": current_user.stripe_customer_id,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────
# CONFIRM PLAN — après SetupIntent confirmé
# Active l'abonnement avec trial 7j
# ─────────────────────────────────────────────
class ConfirmPlanData(BaseModel):
    plan: str
    payment_method_id: str

@router.post("/confirm-plan")
async def confirm_plan(
    data: ConfirmPlanData,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Après que l'user a entré sa CB via Elements,
    on attache la PM et on crée l'abonnement avec trial 7j.
    """
    try:
        if data.plan.upper() == "COACH":
            price_id = STRIPE_PRICE_COACH
        elif data.plan.upper() == "CLUB":
            price_id = STRIPE_PRICE_CLUB
        else:
            raise HTTPException(status_code=400, detail="Invalid plan")

        if not current_user.stripe_customer_id:
            raise HTTPException(status_code=400, detail="No customer ID")

        # Attacher la PM au customer
        stripe.PaymentMethod.attach(
            data.payment_method_id,
            customer=current_user.stripe_customer_id,
        )
        # Définir comme PM par défaut
        stripe.Customer.modify(
            current_user.stripe_customer_id,
            invoice_settings={"default_payment_method": data.payment_method_id},
        )
        # Créer l'abonnement avec trial 7j
        subscription = stripe.Subscription.create(
            customer=current_user.stripe_customer_id,
            items=[{"price": price_id}],
            trial_period_days=7,
            default_payment_method=data.payment_method_id,
            metadata={"user_id": str(current_user.id), "plan": data.plan.upper()},
        )

        # Mettre à jour en base
        from app.models.user import PlanType
        try:
            current_user.plan = PlanType(data.plan.upper())
        except ValueError:
            current_user.plan = PlanType.COACH
        current_user.stripe_subscription_id = subscription.id
        current_user.is_active = True
        db.commit()

        return {
            "success": True,
            "subscription_id": subscription.id,
            "status": subscription.status,
            "trial_end": subscription.trial_end,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

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

    # ── J-3 avant fin trial — rappel email automatique
    elif event['type'] == 'customer.subscription.trial_will_end':
        subscription = event['data']['object']
        user = db.query(User).filter(
            User.stripe_customer_id == subscription['customer']
        ).first()
        if user:
            trial_end_ts = subscription.get('trial_end')
            if trial_end_ts:
                from datetime import timezone
                trial_end_dt = datetime.fromtimestamp(trial_end_ts, tz=timezone.utc)
                debit_date   = trial_end_dt.strftime('%d %B %Y')
                _send_trial_reminder_email(user.email, user.name, debit_date)

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
# UTILISER L'ANALYSE TRIAL
# ─────────────────────────────────────────────
@router.post("/use-trial-match")
async def use_trial_match(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Marque l'analyse trial comme utilisée"""
    current_user.trial_match_used = True
    db.commit()
    return {"success": True}

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
