from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import DATABASE_URL

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Create SessionLocal factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative Base for models
Base = declarative_base()


def get_db():
    """Dependency / context manager helper for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(bind_engine=engine):
    """Create all registered tables in the database."""
    Base.metadata.create_all(bind=bind_engine)


def drop_db(bind_engine=engine):
    """Drop all tables in the database (used for resets/testing)."""
    Base.metadata.drop_all(bind=bind_engine)
