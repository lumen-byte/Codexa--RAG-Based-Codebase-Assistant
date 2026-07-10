from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import DATABASE_URL

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# Production-grade SQLAlchemy Database Engine
# - pool_pre_ping: connection liveness checks (reconnects dead connections)
# - pool_size: number of persistent connections to keep in pool
# - max_overflow: transient connections allowed under heavy load
# - pool_recycle: recycles connection sockets before DB side timeout (refreshes connection pool)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
)

# Session factory for generating database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Modern SQLAlchemy 2.0 Base model class using DeclarativeBase
class Base(DeclarativeBase):
    pass


def get_db():
    """
    FastAPI dependency that provides a transactional database session scope.
    Automatically closes the session after the request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
