from app.database import engine
from sqlalchemy import text

print("🔧 ULTIMATE FIX - DELETING OLD COLUMNS & ENUMS...")

with engine.connect() as conn:
    
    # 1. Drop user_id column from players
    print("1. Removing players.user_id column...")
    try:
        conn.execute(text("ALTER TABLE players DROP COLUMN IF EXISTS user_id"))
        print("   ✅ Removed user_id")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    # 2. Make sure status is VARCHAR and lowercase
    print("2. Converting status to VARCHAR...")
    try:
        conn.execute(text("ALTER TABLE players ALTER COLUMN status TYPE VARCHAR"))
        print("   ✅ status is VARCHAR")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    # 3. Update all existing player status to lowercase
    print("3. Updating status values to lowercase...")
    try:
        conn.execute(text("UPDATE players SET status = lower(status)"))
        print("   ✅ All status values are lowercase")
    except Exception as e:
        print(f"   ⚠️  {e}")
    
    conn.commit()
    
print("\n🎉 DONE!")
print("Now modify player.py model to remove Enum and use String")
