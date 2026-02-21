from app.database import engine
from sqlalchemy import text

print("🔧 FIXING ALL DATABASE ISSUES...")

with engine.connect() as conn:
    # 1. Fix players.position to VARCHAR
    try:
        conn.execute(text("ALTER TABLE players ALTER COLUMN position TYPE VARCHAR USING position::text"))
        print("✅ 1. position → VARCHAR")
    except Exception as e:
        print(f"⚠️ 1. {e}")
    
    # 2. Fix players.status ENUM values (change ACTIVE to ACTIF in existing data)
    try:
        conn.execute(text("UPDATE players SET status = 'actif' WHERE status = 'ACTIVE'"))
        print("✅ 2. Changed ACTIVE → actif in data")
    except Exception as e:
        print(f"⚠️ 2. {e}")
    
    # 3. Convert status column to VARCHAR first
    try:
        conn.execute(text("ALTER TABLE players ALTER COLUMN status TYPE VARCHAR USING status::text"))
        print("✅ 3. status → VARCHAR")
    except Exception as e:
        print(f"⚠️ 3. {e}")
    
    # 4. Add matches.competition column
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS competition VARCHAR"))
        print("✅ 4. Added matches.competition column")
    except Exception as e:
        print(f"⚠️ 4. {e}")
    
    # 5. Add matches.location column
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS location VARCHAR"))
        print("✅ 5. Added matches.location column")
    except Exception as e:
        print(f"⚠️ 5. {e}")
    
    # 6. Add matches.score_home
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS score_home INTEGER"))
        print("✅ 6. Added matches.score_home column")
    except Exception as e:
        print(f"⚠️ 6. {e}")
    
    # 7. Add matches.score_away
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS score_away INTEGER"))
        print("✅ 7. Added matches.score_away column")
    except Exception as e:
        print(f"⚠️ 7. {e}")
    
    # 8. Add matches.weather
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS weather VARCHAR"))
        print("✅ 8. Added matches.weather column")
    except Exception as e:
        print(f"⚠️ 8. {e}")
    
    # 9. Add matches.pitch_type
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS pitch_type VARCHAR"))
        print("✅ 9. Added matches.pitch_type column")
    except Exception as e:
        print(f"⚠️ 9. {e}")
    
    conn.commit()
    print("\n🎉 DONE! Restart backend now.")

if __name__ == "__main__":
    pass
