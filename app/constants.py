"""
constants.py — Source de vérité unique pour les constantes métier Insightball.
Importer depuis ici uniquement. Ne jamais redéfinir ailleurs.
"""

# Quotas par plan — nombre de matchs par cycle Stripe
# Clés string pour compatibilité avec user.plan (PlanType enum et string)
PLAN_QUOTAS: dict[str, int] = {
    "COACH":    4,
    "CLUB":     10,
    "CLUB_PRO": 15,
}

TRIAL_MATCH_LIMIT: int = 1
