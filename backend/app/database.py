import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = "sqlite:///c:/Users/param/OneDrive/Desktop/SBI/backend/saarthi_bfi.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    account_number = Column(String, unique=True, index=True)
    name = Column(String)
    primary_language = Column(String, default="en") # 'en', 'hi', 'ta', etc.
    registered_at = Column(DateTime, default=datetime.utcnow)
    current_dcs = Column(Float, default=50.0) # Digital Confidence Score
    current_dcs_band = Column(String, default="Developing") # 'Dormant', 'Cautious', 'Developing', 'Confident', 'Advocate'

    telemetry = relationship("SessionTelemetry", back_populates="user")
    interventions = relationship("Intervention", back_populates="user")
    escalations = relationship("StaffQueue", back_populates="user")

class SessionTelemetry(Base):
    __tablename__ = "session_telemetry"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    session_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    feature_name = Column(String) # 'balance_check', 'upi_transfer', 'recurring_deposit', 'mutual_funds', 'insurance'
    action = Column(String) # 'visit', 'dwell', 'attempt', 'complete', 'dismiss', 'exit_without_action'
    dwell_time = Column(Float, default=0.0) # in seconds
    error_occurred = Column(Boolean, default=False)
    error_message = Column(String, nullable=True)

    user = relationship("User", back_populates="telemetry")

class Intervention(Base):
    __tablename__ = "interventions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    session_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    feature_name = Column(String)
    gap_type = Column(String) # 'Awareness', 'Confidence', 'Access', 'Language'
    dcs_at_intervention = Column(Float)
    mode_triggered = Column(Integer) # 1, 2, 3, 4
    message_delivered = Column(String)
    outcome = Column(String, default="pending") # 'completed', 'dismissed', 'ignored', 'pending'
    resolved_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="interventions")

class StaffQueue(Base):
    __tablename__ = "staff_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    escalated_at = Column(DateTime, default=datetime.utcnow)
    feature_name = Column(String)
    reason_code = Column(String) # 'ACCESS_ERR', 'MULTIPLE_DISMISSALS', 'LOW_DCS_ABANDONMENT'
    context_summary = Column(String) # Pre-filled card summary
    status = Column(String, default="pending") # 'pending', 'called', 'resolved'
    executive_notes = Column(String, nullable=True)

    user = relationship("User", back_populates="escalations")

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
