from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
import uuid

# SQLite stores the database locally in the same directory under careerlens.db
DATABASE_URL = "sqlite:///./careerlens.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    # A secure universally unique identifier for the user account / device
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    
    # Two-Phase Credit Commit Infrastructure
    available_credits = Column(Integer, default=5) # Grant 5 starter credits
    locked_credits = Column(Integer, default=0)

# Create all tables on boot
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
