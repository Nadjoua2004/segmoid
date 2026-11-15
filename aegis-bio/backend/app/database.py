"""
Database Configuration and Session Management
SQLite Engine & Session Local setup for Aegis-Bio
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

def _database_url(url: str) -> str:
    """Supabase/Heroku-style "postgres://" URLs -> the SQLAlchemy psycopg2 dialect name."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _database_url(settings.DATABASE_URL)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    # SQLite connect_args needed for multithreading in FastAPI
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)
else:
    # Hosted Postgres (Supabase in production): drop dead pooled connections instead of failing a request
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300, pool_size=5, max_overflow=5,
                           echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """FastAPI Dependency for database session management."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Create all database tables and migrate missing columns if needed."""
    import app.models  # Ensure models are loaded
    Base.metadata.create_all(bind=engine)

    # Lightweight migration for existing SQLite database instances
    if IS_SQLITE:
        with engine.connect() as conn:
            from sqlalchemy import text
            existing_cols = [
                row[1] for row in conn.execute(text("PRAGMA table_info(emergency_alerts);")).fetchall()
            ]
            columns_to_add = [
                ("user_id", "INTEGER"),
                ("crew_name", "VARCHAR(64) DEFAULT 'CREW-A'"),
                ("station_name", "VARCHAR(120) DEFAULT 'LUNAR-BASE-ALPHA'"),
                ("status", "VARCHAR(32) DEFAULT 'PENDING_OWNER'"),
                ("timeout_seconds", "INTEGER DEFAULT 60"),
                ("timeout_at", "DATETIME"),
                ("emergency_contact_name", "VARCHAR(120)"),
                ("emergency_contact_callsign", "VARCHAR(64)"),
                ("emergency_contact_email", "VARCHAR(120)"),
                ("emergency_contact_phone", "VARCHAR(64)"),
                ("emergency_contact_role", "VARCHAR(64)"),
                ("emergency_contact_notified_at", "DATETIME"),
                ("source", "VARCHAR(64) DEFAULT 'SYSTEM'"),
                ("requires_action", "BOOLEAN DEFAULT 1"),
                ("prediction_data", "TEXT"),
                ("owner_answered", "BOOLEAN DEFAULT 0"),
            ]
            for col_name, col_type in columns_to_add:
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE emergency_alerts ADD COLUMN {col_name} {col_type};"))
                        conn.commit()
                    except Exception:
                        pass

            # Migration for users table
            user_cols = [
                row[1] for row in conn.execute(text("PRAGMA table_info(users);")).fetchall()
            ]
            user_columns_to_add = [
                ("is_lead", "BOOLEAN DEFAULT 0"),
                ("crew_name", "VARCHAR(64) DEFAULT 'CREW-A'"),
                ("station_name", "VARCHAR(120) DEFAULT 'LUNAR-BASE-ALPHA'"),
                ("alert_timeout_seconds", "INTEGER DEFAULT 60"),
                ("environment", "VARCHAR(24) DEFAULT 'LUNAR'"),
            ]
            for col_name, col_type in user_columns_to_add:
                if col_name not in user_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};"))
                        conn.commit()
                    except Exception:
                        pass
