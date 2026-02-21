import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superadmin BOOLEAN DEFAULT FALSE NOT NULL;"))
    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP;"))
    conn.commit()
    print("✅ Colonnes ajoutées")

with engine.connect() as conn:
    conn.execute(text("UPDATE users SET is_superadmin = TRUE WHERE email = 'contact@insightball.com'"))
    conn.commit()
    print("✅ Compte contact@insightball.com promu superadmin")
