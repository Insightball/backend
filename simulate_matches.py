from sqlalchemy import create_engine, text
import os, uuid, random
from datetime import datetime, timedelta

DATABASE_URL = "postgresql://insightball_db_user:xeOYv3mjw4cGVlqCI9JMBvJGEADs1UUj@dpg-d6cpvf75r7bs73ajcpsg-a.oregon-postgres.render.com/insightball_db"
engine = create_engine(DATABASE_URL)

MATCHES = [
    {"opponent": "FC Muret U14",         "date_offset": -90, "score_home": 3, "score_away": 1, "competition": "Championnat District", "location": "Stade de Cugnaux"},
    {"opponent": "Toulouse FC U14",      "date_offset": -75, "score_home": 1, "score_away": 2, "competition": "Championnat District", "location": "Stade Antoine Béguère"},
    {"opponent": "US Colomiers U14",     "date_offset": -60, "score_home": 4, "score_away": 0, "competition": "Championnat District", "location": "Stade de Cugnaux"},
    {"opponent": "SC Tournefeuille U14", "date_offset": -45, "score_home": 2, "score_away": 2, "competition": "Championnat District", "location": "Stade Pierre Baudis"},
    {"opponent": "AS Plaisance U14",     "date_offset": -30, "score_home": 5, "score_away": 1, "competition": "Coupe du District",    "location": "Stade de Cugnaux"},
    {"opponent": "FC Portet U14",        "date_offset": -15, "score_home": 2, "score_away": 3, "competition": "Championnat District", "location": "Stade Jean Pégot"},
    {"opponent": "AS Seysses U14",       "date_offset": -7,  "score_home": 3, "score_away": 0, "competition": "Championnat District", "location": "Stade de Cugnaux"},
]

with engine.connect() as conn:
    club_id = conn.execute(text("SELECT club_id FROM users WHERE email = 'ryad.bouharaoua@gmail.com'")).fetchone()[0]
    print(f"Club ID: {club_id}")

    conn.execute(text("DELETE FROM matches WHERE club_id = :c"), {"c": club_id})
    print("Anciens matchs supprimés")

    for m in MATCHES:
        mid = str(uuid.uuid4())
        d = datetime.now() + timedelta(days=m["date_offset"])
        pos = random.randint(48, 68)
        pas = random.randint(120, 280)
        shots = m["score_home"] * 3 + random.randint(2, 8)
        sot = m["score_home"] + random.randint(1, 4)
        stats = f'{{"possession": {pos}, "passes": {pas}, "shots": {shots}, "shots_on_target": {sot}}}'

        conn.execute(text("""
            INSERT INTO matches (id, club_id, opponent, date, competition, location, category, score_home, score_away, status, stats, created_at)
            VALUES (:id, :club_id, :opponent, :date, :competition, :location, :category, :sh, :sa, 'COMPLETED', :stats, NOW())
        """), {
            "id": mid, "club_id": club_id,
            "opponent": m["opponent"], "date": d,
            "competition": m["competition"], "location": m["location"],
            "category": "U14",
            "sh": m["score_home"], "sa": m["score_away"],
            "stats": stats,
        })
        print(f"✅ {m['opponent']} {m['score_home']}-{m['score_away']}")

    conn.commit()
    print("\n🎉 7 matchs créés avec succès !")
