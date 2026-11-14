"""
Database Configuration and Session Management
SQLite Engine & Session Local setup for Aegis-Bio
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

# SQLite connect_args needed for multithreading in FastAPI
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

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
    if "sqlite" in settings.DATABASE_URL:
        with engine.connect() as conn:
            from sqlalchemy import text
            existing_cols = [
                row[1] for row in conn.execute(text("PRAGMA table_info(emergency_alerts);")).fetchall()
            ]
            columns_to_add = [
                ("user_id", "INTEGER"),
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
