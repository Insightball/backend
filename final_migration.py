from app.database import engine
from sqlalchemy import text

print("🔧 FINAL DATABASE MIGRATION...")
print("⚠️  This will fix all ENUM and column issues\n")

with engine.connect() as conn:
    
    # 1. DROP playerstatus ENUM and recreate
    print("1. Fixing players.status ENUM...")
    try:
        # Set all existing players to a temporary value
        conn.execute(text("ALTER TABLE players ALTER COLUMN status TYPE VARCHAR"))
        conn.execute(text("UPDATE players SET status = 'actif' WHERE status IN ('ACTIVE', 'ACTIF')"))
        conn.execute(text("UPDATE players SET status = 'blessé' WHERE status IN ('BLESSE', 'BLESSÉ')"))
        print("   ✅ Fixed status column")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    # 2. Fix position to VARCHAR
    print("2. Converting players.position to VARCHAR...")
    try:
        conn.execute(text("ALTER TABLE players ALTER COLUMN position TYPE VARCHAR USING position::text"))
        print("   ✅ position is now VARCHAR")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    # 3. Add missing matches columns
    print("3. Adding missing matches columns...")
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS competition VARCHAR"))
        print("   ✅ Added matches.competition")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS location VARCHAR"))
        print("   ✅ Added matches.location")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS score_home INTEGER"))
        print("   ✅ Added matches.score_home")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS score_away INTEGER"))
        print("   ✅ Added matches.score_away")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS weather VARCHAR"))
        print("   ✅ Added matches.weather")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS pitch_type VARCHAR"))
        print("   ✅ Added matches.pitch_type")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    # 4. Add lineup column
    print("4. Adding matches.lineup column...")
    try:
        conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS lineup JSON"))
        print("   ✅ Added matches.lineup")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    conn.commit()
    
print("\n🎉 MIGRATION COMPLETE!")
print("✅ Now restart your backend: python main.py")
