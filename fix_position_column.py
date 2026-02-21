from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text("ALTER TABLE players ALTER COLUMN position TYPE VARCHAR USING position::text"))
    conn.commit()
    print("✅ FAIT")
