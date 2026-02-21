from app.database import engine
from sqlalchemy import text

def migrate():
    print("🔄 Adding 'lineup' column to matches table...")
    
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE matches ADD COLUMN IF NOT EXISTS lineup JSON"))
            conn.commit()
            print("✅ Column 'lineup' added successfully")
        except Exception as e:
            print(f"⚠️ Error: {e}")

if __name__ == "__main__":
    migrate()
