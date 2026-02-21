from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text("SELECT name, number, position, status FROM players ORDER BY number"))
    
    print("\n📋 TOUS LES JOUEURS DANS LA DB :")
    print("-" * 60)
    for row in result:
        print(f"#{row[1]:2} | {row[0]:20} | {row[2]:15} | {row[3]}")
    print("-" * 60)
