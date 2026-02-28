from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import stripe
import os
from datetime import datetime, timezone

from app.database import get_db
from app.models import User
from app.dependencies import get_current_active_user
from pydantic import BaseModel

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# ⚠️  Mettre à jour dans Render > Environment Variables
STRIPE_PRICE_COACH = os.getenv("STRIPE_PRICE_COACH", "price_coach_39")
STRIPE_PRICE_CLUB  = os.getenv("STRIPE_PRICE_CLUB",  "price_club_129")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _plan_to_price(plan: str) -> str:
    p = plan.upper()
    if p == "COACH": return STRIPE_PRICE_COACH
    if p == "CLUB":  return STRIPE_PRICE_CLUB
    raise HTTPException(status_code=400, detail="Invalid plan")

def _plan_value(user):
    return user.plan.value if hasattr(user.plan, 'value') else user.plan

def _send_trial_welcome_email(to_email: str, name: str, trial_end: int):
    """Email de bienvenue apres activation du trial. Non bloquant."""
    import httpx
    resend_key = os.getenv("RESEND_API_KEY")
    if not resend_key:
        print(f"[WARN] RESEND_API_KEY manquant — welcome email non envoye a {to_email}")
        return
    try:
        first_name = name.split()[0] if name else "Coach"
        debit_str = ""
        if trial_end:
            debit_str = datetime.fromtimestamp(trial_end, tz=timezone.utc).strftime("%d %B %Y")
        debit_line = (
            f'<p style="font-size:12px;color:rgba(15,15,13,0.45);margin:16px 0;">'
            f'Votre carte sera debitee le <strong>{debit_str}</strong> sauf resiliation avant cette date.</p>'
        ) if debit_str else ""
        resp = httpx.post(
            "https://api.resend.com/emails",
            json={
                "from":    "InsightBall <contact@insightball.com>",
                "to":      [to_email],
                "subject": "Votre essai InsightBall est active - 1 match offert",
                "html": f"""
                <div style="font-family:monospace;max-width:520px;margin:0 auto;padding:32px 24px;background:#faf8f4;">
                  <div style="font-size:22px;font-weight:900;text-transform:uppercase;letter-spacing:.04em;margin-bottom:24px;">
                    INSIGHT<span style="color:#c9a227;">BALL</span>
                  </div>
                  <p style="font-size:15px;color:#2a2a26;line-height:1.6;">Bonjour {first_name},</p>
                  <p style="font-size:14px;color:#2a2a26;line-height:1.7;">
                    Votre essai gratuit est active. Vous avez <strong>7 jours</strong> et <strong>1 match offert</strong> pour decouvrir InsightBall.
                  </p>
                  <div style="background:#fff;border:1px solid rgba(15,15,13,0.09);border-left:3px solid #c9a227;padding:14px 18px;margin:20px 0;">
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#c9a227;margin-bottom:8px;">Ce qui vous attend</div>
                    <div style="font-size:12px;color:rgba(15,15,13,0.65);line-height:1.8;">
                      - Uploadez votre video de match<br/>
                      - Recevez un rapport tactique complet<br/>
                      - Heatmaps, stats individuelles et collectives<br/>
                      - Export PDF
                    </div>
                  </div>
                  {debit_line}
                  <a href="https://insightball.com/dashboard/matches/upload"
                     style="display:inline-block;padding:12px 24px;background:#c9a227;color:#0f0f0d;font-size:11px;letter-spacing:.1em;text-transform:uppercase;font-weight:700;text-decoration:none;margin-top:8px;">
                    Analyser mon premier match
                  </a>
                  <p style="font-size:11px;color:rgba(15,15,13,0.35);margin-top:28px;line-height:1.6;">
                    InsightBall - contact@insightball.com<br/>
                    Resiliation : Parametres - Gerer mon abonnement
                  </p>
                </div>
                """,
            },
            headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            print(f"[WARN] Resend welcome failed {resp.status_code}: {resp.text}")
        else:
            print(f"[INFO] Welcome email envoye a {to_email}")
    except Exception as e:
        print(f"[ERR] Welcome email failed: {e}")


def _send_trial_reminder_email(to_email: str, name: str, debit_date: str):
    """Rappel J-3 avant fin trial via Resend. Non bloquant."""
    import httpx
    resend_key = os.getenv("RESEND_API_KEY")
    if not resend_key:
        print(f"[WARN] RESEND_API_KEY manquant — email non envoyé à {to_email}")
        return
    try:
        first_name = name.split()[0] if name else "Coach"
        resp = httpx.post(
            "https://api.resend.com/emails",
            json={
                "from":    "InsightBall <contact@insightball.com>",
                "to":      [to_email],
                "subject": "Votre essai InsightBall se termine dans 2 jours",
                "html": f"""
                <div style="font-family:monospace;max-width:520px;margin:0 auto;padding:32px 24px;background:#faf8f4;">
                  <div style="font-size:22px;font-weight:900;text-transform:uppercase;letter-spacing:.04em;margin-bottom:24px;">
                    INSIGHT<span style="color:#c9a227;">BALL</span>
                  </div>
                  <p style="font-size:15px;color:#2a2a26;line-height:1.6;">Bonjour {first_name},</p>
                  <p style="font-size:14px;color:#2a2a26;line-height:1.7;">
                    Votre essai gratuit se termine dans <strong>2 jours</strong>.<br>
                    Votre carte bancaire sera débitée le <strong>{debit_date}</strong> sauf résiliation avant cette date.
                  </p>
                  <div style="background:#fff;border:1px solid rgba(15,15,13,0.09);border-left:3px solid #c9a227;padding:14px 18px;margin:20px 0;">
                    <p style="font-size:12px;color:rgba(15,15,13,0.55);margin:0;line-height:1.6;">
                      Pour annuler : connectez-vous sur insightball.com → Paramètres → Gérer mon abonnement.<br>
                      Aucune question posée, résiliation en 1 clic.
                    </p>
                  </div>
                  <a href="https://insightball.com/dashboard/settings"
                     style="display:inline-block;padding:12px 24px;background:#c9a227;color:#0f0f0d;font-size:11px;letter-spacing:.1em;text-transform:uppercase;font-weight:700;text-decoration:none;margin-top:8px;">
                    Gérer mon abonnement →
                  </a>
                  <p style="font-size:11px;color:rgba(15,15,13,0.35);margin-top:28px;line-height:1.6;">
                    InsightBall · contact@insightball.com
                  </p>
                </div>
                """,
            },
            headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            print(f"[WARN] Resend failed {resp.status_code}: {resp.text}")
        else:
            print(f"[INFO] Rappel trial envoyé à {to_email}")
    except Exception as e:
        print(f"[ERR] Email reminder failed: {e}")


# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────
class CheckoutSessionCreate(BaseModel):
    plan: str
    success_url: str
    cancel_url: str

class PortalSessionCreate(BaseModel):
    return_url: str

class ConfirmPlanData(BaseModel):
    plan: str
    payment_method_id: str


# ─────────────────────────────────────────────
# CB ENREGISTRÉE ? — vérifie avant upload
# ─────────────────────────────────────────────
@router.get("/has-payment-method")
async def has_payment_method(
    current_user: User = Depends(get_current_active_user),
):
    """Utilisé par UploadMatch pour bloquer l'accès si pas de CB."""
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
    """Crée un SetupIntent pour enregistrer la CB sans débit immédiat."""
    try:
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
# Active l'abonnement avec trial 7j (Coach ET Club)
# L'essai démarre ICI — pas à l'inscription
# ─────────────────────────────────────────────
@router.post("/confirm-plan")
async def confirm_plan(
    data: ConfirmPlanData,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Appelé après confirmation CB via Stripe Elements.
    Attache la PM, crée l'abonnement avec trial 7j.
    Le compteur trial démarre maintenant — pas à l'inscription.
    """
    try:
        price_id = _plan_to_price(data.plan)

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
        # Trial 7j accordé UNIQUEMENT au plan COACH
        # Le plan CLUB est vendu sur devis — pas de trial automatique
        sub_params: dict = dict(
            customer=current_user.stripe_customer_id,
            items=[{"price": price_id}],
            default_payment_method=data.payment_method_id,
            metadata={"user_id": str(current_user.id), "plan": data.plan.upper()},
        )
        if data.plan.upper() == "COACH" and not current_user.trial_ends_at:
            sub_params["trial_period_days"] = 7

        subscription = stripe.Subscription.create(**sub_params)

        # Mettre à jour en base
        from app.models.user import PlanType
        try:
            current_user.plan = PlanType(data.plan.upper())
        except ValueError:
            current_user.plan = PlanType.COACH
        current_user.stripe_subscription_id = subscription.id
        current_user.is_active = True
        # Stocker la date de fin de trial en base pour le quota check (UTC naive)
        if subscription.trial_end:
            current_user.trial_ends_at = datetime.fromtimestamp(
                subscription.trial_end, tz=timezone.utc
            ).replace(tzinfo=None)
        db.commit()

        # Email de bienvenue — trial activé (non bloquant)
        _send_trial_welcome_email(
            to_email=current_user.email,
            name=current_user.name or "Coach",
            trial_end=subscription.trial_end,
        )

        return {
            "success": True,
            "subscription_id": subscription.id,
            "status": subscription.status,
            "trial_end": subscription.trial_end,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────
# CHECKOUT SESSION — flow Stripe hosted
# Utilisé par TrialExpired et SubscriptionPlans
# FIX : pas de second trial si l'user en a déjà eu un
# ─────────────────────────────────────────────
@router.post("/create-checkout-session")
async def create_checkout_session(
    data: CheckoutSessionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        price_id = _plan_to_price(data.plan)

        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={"user_id": str(current_user.id), "name": current_user.name}
            )
            current_user.stripe_customer_id = customer.id
            db.commit()

        # RÈGLE BUSINESS : le trial 7j est réservé au plan COACH uniquement.
        # Le plan CLUB est vendu sur devis — il ne passe jamais par create-checkout-session.
        if data.plan.upper() != "COACH":
            raise HTTPException(
                status_code=400,
                detail="Le plan CLUB est disponible sur devis uniquement. Contactez contact@insightball.com"
            )

        # FIX P0 — Pas de second trial si l'user en a déjà eu un.
        already_trialed = current_user.trial_ends_at is not None
        subscription_data: dict = {
            "metadata": {"user_id": str(current_user.id), "plan": "COACH"}
        }
        if not already_trialed:
            subscription_data["trial_period_days"] = 7

        checkout_session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            subscription_data=subscription_data,
            success_url=data.success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=data.cancel_url,
            metadata={"user_id": str(current_user.id), "plan": data.plan.upper()}
        )
        return {"session_id": checkout_session.id, "url": checkout_session.url}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────
# TRIAL STATUS
# Source de vérité = Stripe uniquement
# Si pas de sub Stripe → "no_trial" (pas de CB enregistrée)
# ─────────────────────────────────────────────
@router.get("/trial-status")
async def get_trial_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Retourne l'état du trial.
    - "full"     : abonnement actif (trialing ou active)
    - "no_trial" : pas de CB enregistrée → doit s'abonner
    - "expired"  : sub annulé ou inexistant après période
    Source de vérité = Stripe. Pas de fallback created_at.
    """
    now = datetime.now(tz=timezone.utc)

    # A un sub Stripe → interroger Stripe
    if current_user.stripe_subscription_id:
        try:
            sub = stripe.Subscription.retrieve(current_user.stripe_subscription_id)
            sub_dict = sub.to_dict() if hasattr(sub, 'to_dict') else dict(sub)
            status = sub_dict.get('status')

            if status in ('active', 'trialing'):
                trial_end_ts = sub_dict.get('trial_end')
                days_left = 0
                if trial_end_ts and status == 'trialing':
                    trial_end_dt = datetime.fromtimestamp(trial_end_ts, tz=timezone.utc)
                    days_left = max(0, (trial_end_dt - now).days)
                return {
                    "access": "full",
                    "status": status,
                    "trial_active": status == 'trialing',
                    "days_left": days_left,
                    "trial_ends_at": trial_end_ts,
                    "match_used": getattr(current_user, 'trial_match_used', False),
                    "plan": _plan_value(current_user),
                }
            else:
                return {
                    "access": "expired",
                    "trial_active": False,
                    "days_left": 0,
                    "match_used": getattr(current_user, 'trial_match_used', False),
                    "plan": None,
                }
        except stripe.error.StripeError:
            pass

    # Pas de sub Stripe → vérifier si customer avec sub actif
    if current_user.stripe_customer_id:
        try:
            subs = stripe.Subscription.list(
                customer=current_user.stripe_customer_id,
                limit=1
            )
            if subs.data:
                sub = subs.data[0]
                if sub.status in ('active', 'trialing'):
                    # Mettre à jour subscription_id en base
                    current_user.stripe_subscription_id = sub.id
                    db.commit()
                    trial_end_ts = sub.trial_end
                    days_left = 0
                    if trial_end_ts and sub.status == 'trialing':
                        trial_end_dt = datetime.fromtimestamp(trial_end_ts, tz=timezone.utc)
                        days_left = max(0, (trial_end_dt - now).days)
                    return {
                        "access": "full",
                        "status": sub.status,
                        "trial_active": sub.status == 'trialing',
                        "days_left": days_left,
                        "trial_ends_at": trial_end_ts,
                        "match_used": getattr(current_user, 'trial_match_used', False),
                        "plan": _plan_value(current_user),
                    }
        except stripe.error.StripeError:
            pass

    # Aucun sub, aucune CB → pas encore d'essai
    return {
        "access": "no_trial",
        "trial_active": False,
        "days_left": 0,
        "match_used": False,
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
    sub_id = current_user.stripe_subscription_id

    if not sub_id and current_user.stripe_customer_id:
        try:
            subs = stripe.Subscription.list(
                customer=current_user.stripe_customer_id,
                limit=1
            )
            if subs.data:
                sub = subs.data[0]
                return {
                    "active": sub.status in ('active', 'trialing'),
                    "plan": _plan_value(current_user),
                    "status": sub.status,
                    "current_period_end": sub.current_period_end,
                    "cancel_at_period_end": sub.cancel_at_period_end,
                }
        except stripe.error.StripeError:
            pass
        return {"active": False, "plan": _plan_value(current_user), "status": "inactive"}

    if not sub_id:
        return {"active": False, "plan": _plan_value(current_user), "status": "inactive"}

    try:
        sub = stripe.Subscription.retrieve(sub_id)
        sub_dict = sub.to_dict() if hasattr(sub, 'to_dict') else dict(sub)

        period_end = sub_dict.get('current_period_end')
        try:
            items_data = sub_dict.get('items', {}).get('data', [])
            if items_data:
                period_end = items_data[0].get('current_period_end') or period_end
        except Exception:
            pass

        return {
            "active": sub_dict.get('status') in ('active', 'trialing'),
            "plan": _plan_value(current_user),
            "status": sub_dict.get('status'),
            "current_period_end": period_end,
            "cancel_at_period_end": sub_dict.get('cancel_at_period_end', False),
        }
    except stripe.error.StripeError as e:
        return {"active": False, "plan": _plan_value(current_user), "status": "error", "error": str(e)}


# ─────────────────────────────────────────────
# WEBHOOKS STRIPE
# ─────────────────────────────────────────────
@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload        = await request.body()
    sig_header     = request.headers.get('stripe-signature')
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
            # Récupérer trial_end depuis le sub Stripe (UTC naive)
            sub_id = session.get('subscription')
            if sub_id:
                try:
                    sub = stripe.Subscription.retrieve(sub_id)
                    if sub.trial_end:
                        user.trial_ends_at = datetime.fromtimestamp(
                            sub.trial_end, tz=timezone.utc
                        ).replace(tzinfo=None)
                except Exception:
                    pass
            db.commit()

    # ── J-3 avant fin trial — email de rappel automatique via Resend
    elif event['type'] == 'customer.subscription.trial_will_end':
        subscription = event['data']['object']
        user = db.query(User).filter(
            User.stripe_customer_id == subscription['customer']
        ).first()
        if user:
            trial_end_ts = subscription.get('trial_end')
            if trial_end_ts:
                trial_end_dt = datetime.fromtimestamp(trial_end_ts, tz=timezone.utc)
                debit_date   = trial_end_dt.strftime('%d %B %Y')
                _send_trial_reminder_email(user.email, user.name, debit_date)

    # ── Premier prélèvement réussi après trial
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        if invoice.get('billing_reason') in ('subscription_cycle', 'subscription_create'):
            user = db.query(User).filter(
                User.stripe_customer_id == invoice['customer']
            ).first()
            if user:
                user.is_active = True
                db.commit()

    # ── Paiement échoué
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        user = db.query(User).filter(
            User.stripe_customer_id == invoice['customer']
        ).first()
        if user:
            user.is_active = False
            db.commit()

    # ── Abonnement annulé (fin de période ou immédiat)
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        user = db.query(User).filter(
            User.stripe_customer_id == subscription['customer']
        ).first()
        if user:
            user.is_active = False
            user.stripe_subscription_id = None
            db.commit()

    # ── Abonnement mis à jour (trialing → active, upgrade, cancel_at_period_end)
    # FIX P0 — C'est ici la source de vérité pour le plan, pas dans upgrade-plan
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        user = db.query(User).filter(
            User.stripe_customer_id == subscription['customer']
        ).first()
        if user:
            user.is_active = subscription['status'] in ('active', 'trialing')
            plan_str = subscription.get('metadata', {}).get('plan', '').upper()
            if plan_str in ('COACH', 'CLUB'):
                from app.models.user import PlanType
                try:
                    user.plan = PlanType(plan_str)
                except ValueError:
                    pass
            db.commit()

    return {"status": "success"}


# ─────────────────────────────────────────────
# REQUEST CLUB QUOTE
# Le plan CLUB est vendu sur devis — pas d'upgrade automatique.
# Cet endpoint envoie un email de demande de devis via Resend.
# Un admin contacte l'utilisateur et crée le sub manuellement depuis le dashboard Stripe.
# ─────────────────────────────────────────────
class ClubQuoteRequest(BaseModel):
    message: str = ""  # Message optionnel du coach

@router.post("/request-club-quote")
async def request_club_quote(
    data: ClubQuoteRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Envoie une demande de devis CLUB par email via Resend.
    Pas de création de subscription Stripe — traitement manuel par l'équipe InsightBall.
    """
    import httpx
    resend_key = os.getenv("RESEND_API_KEY")
    if not resend_key:
        raise HTTPException(status_code=500, detail="Service email non configuré")

    plan_value = _plan_value(current_user)
    profile_phone = getattr(current_user, 'profile_phone', '') or ''
    profile_club  = getattr(current_user, 'profile_city', '') or ''

    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            json={
                "from":    "InsightBall <contact@insightball.com>",
                "to":      ["contact@insightball.com"],
                "subject": f"Demande de devis CLUB — {current_user.name}",
                "html": f"""
                <div style="font-family:monospace;max-width:520px;margin:0 auto;padding:32px 24px;background:#faf8f4;">
                  <div style="font-size:22px;font-weight:900;text-transform:uppercase;letter-spacing:.04em;margin-bottom:24px;">
                    INSIGHT<span style="color:#c9a227;">BALL</span> — Devis CLUB
                  </div>
                  <table style="width:100%;border-collapse:collapse;font-size:13px;">
                    <tr><td style="padding:6px 0;color:#888;width:120px;">Nom</td><td style="padding:6px 0;font-weight:700;">{current_user.name}</td></tr>
                    <tr><td style="padding:6px 0;color:#888;">Email</td><td style="padding:6px 0;">{current_user.email}</td></tr>
                    <tr><td style="padding:6px 0;color:#888;">Téléphone</td><td style="padding:6px 0;">{profile_phone or 'Non renseigné'}</td></tr>
                    <tr><td style="padding:6px 0;color:#888;">Ville / Club</td><td style="padding:6px 0;">{profile_club or 'Non renseigné'}</td></tr>
                    <tr><td style="padding:6px 0;color:#888;">Plan actuel</td><td style="padding:6px 0;">{plan_value}</td></tr>
                    <tr><td style="padding:6px 0;color:#888;">User ID</td><td style="padding:6px 0;font-size:11px;">{current_user.id}</td></tr>
                  </table>
                  {f'<div style="margin-top:16px;padding:12px 16px;background:#fff;border-left:3px solid #c9a227;"><strong>Message :</strong><br>{data.message}</div>' if data.message else ''}
                  <p style="margin-top:20px;font-size:11px;color:#aaa;">Répondre à : {current_user.email}</p>
                </div>
                """,
                "reply_to": current_user.email,
            },
            headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            print(f"[WARN] Resend club quote failed {resp.status_code}: {resp.text}")
            raise HTTPException(status_code=500, detail="Erreur envoi email")

        return {"success": True, "message": "Votre demande de devis a été envoyée. Nous vous contacterons sous 24h."}

    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Erreur réseau : {e}")


# ─────────────────────────────────────────────
# ANNULATION (cancel_at_period_end)
# Fonctionne en trial ET en actif
# ─────────────────────────────────────────────
@router.post("/cancel-subscription")
async def cancel_subscription(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    En trial   → annule avant le premier débit (aucun prélèvement)
    En actif   → actif jusqu'à la fin de la période payée
    """
    sub_id = current_user.stripe_subscription_id

    # Chercher le sub si pas en base
    if not sub_id and current_user.stripe_customer_id:
        try:
            subs = stripe.Subscription.list(
                customer=current_user.stripe_customer_id,
                status='trialing',
                limit=1
            )
            if subs.data:
                sub_id = subs.data[0].id
                current_user.stripe_subscription_id = sub_id
                db.commit()
        except stripe.error.StripeError:
            pass

    if not sub_id:
        raise HTTPException(status_code=400, detail="No active subscription")

    try:
        subscription = stripe.Subscription.modify(
            sub_id,
            cancel_at_period_end=True
        )
        return {"success": True, "cancel_at": subscription.cancel_at}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
