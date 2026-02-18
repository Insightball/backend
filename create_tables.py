from app.database import Base, engine
from app.models import User, Club, Match, Player

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Tables created successfully!")
