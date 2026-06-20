from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Dict, Any

from backend.app.database import init_db, get_db, User, SessionTelemetry, Intervention, StaffQueue
from backend.app.models import (
    TelemetryEvent, InterventionResponse, OutcomeRequest, 
    StaffQueueItem, UserProfileResponse, DCSComponentBreakdown
)
from backend.app.dcs_calculator import calculate_user_dcs, update_user_dcs, get_dcs_band
from backend.app.classifier import classify_friction
from backend.app.state_machine import get_next_intervention_mode
from backend.app.data_gen import generate_synthetic_data

app = FastAPI(title="Saarthi BFI Platform API", version="1.0.0")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    # Initialize DB tables and seed synthetic data
    init_db()
    db = next(get_db())
    try:
        generate_synthetic_data(db, 100)
    finally:
        db.close()

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/users")
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [{"account_number": u.account_number, "name": u.name, "current_dcs": u.current_dcs, "current_dcs_band": u.current_dcs_band, "primary_language": u.primary_language} for u in users]

@app.get("/api/users/{account_number}", response_model=UserProfileResponse)

def get_user_profile(account_number: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.account_number == account_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    score, breakdown = calculate_user_dcs(db, user.id)
    return UserProfileResponse(
        account_number=user.account_number,
        name=user.name,
        primary_language=user.primary_language,
        current_dcs=score,
        current_dcs_band=get_dcs_band(score),
        components=DCSComponentBreakdown(
            feature_breadth=breakdown["feature_breadth"],
            completion_rate=breakdown["completion_rate"],
            hesitation_decay=breakdown["hesitation_decay"],
            return_rate=breakdown["return_rate"]
        )
    )

@app.post("/api/telemetry", response_model=InterventionResponse)
def post_telemetry(event: TelemetryEvent, db: Session = Depends(get_db)):
    # 1. Fetch or create User
    user = db.query(User).filter(User.account_number == event.account_number).first()
    if not user:
        # Auto-create user for simple demo flow
        user = User(
            account_number=event.account_number,
            name=f"Customer {event.account_number[-4:]}",
            primary_language="en"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # 2. Log Telemetry Event
    telemetry_entry = SessionTelemetry(
        user_id=user.id,
        session_id=event.session_id,
        feature_name=event.feature_name,
        action=event.action,
        dwell_time=event.dwell_time,
        error_occurred=event.error_occurred,
        error_message=event.error_message,
        timestamp=datetime.utcnow()
    )
    db.add(telemetry_entry)
    db.commit()

    # Recalculate DCS on telemetry event (reflects real-time state changes)
    user = update_user_dcs(db, user)

    # 3. Friction Classifier Engine
    gap_type, classifier_confidence, rule_path = classify_friction(db, user, event.session_id, event.feature_name)

    # 4. State Machine / Response Orchestration
    mode, message = get_next_intervention_mode(db, user, event.session_id, gap_type, event.feature_name)

    should_intervene = False
    if mode in [1, 2]:
        should_intervene = True
        # Log the intervention as pending outcome
        intervention_entry = Intervention(
            user_id=user.id,
            session_id=event.session_id,
            feature_name=event.feature_name,
            gap_type=gap_type,
            dcs_at_intervention=user.current_dcs,
            mode_triggered=mode,
            message_delivered=message,
            outcome="pending",
            timestamp=datetime.utcnow()
        )
        db.add(intervention_entry)
        db.commit()

    return InterventionResponse(
        should_intervene=should_intervene,
        mode=mode,
        gap_type=gap_type,
        message=message if should_intervene else f"No intervention. State: Mode {mode} ({message})",
        language=user.primary_language,
        target_feature=event.feature_name,
        dcs=user.current_dcs,
        current_dcs_band=user.current_dcs_band
    )

@app.post("/api/outcome")
def post_outcome(request: OutcomeRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.account_number == request.account_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find the pending intervention for this user, session, and feature
    pending_intervention = db.query(Intervention).filter(
        Intervention.user_id == user.id,
        Intervention.session_id == request.session_id,
        Intervention.feature_name == request.feature_name,
        Intervention.mode_triggered == request.mode,
        Intervention.outcome == "pending"
    ).order_by(Intervention.timestamp.desc()).first()

    if not pending_intervention:
        # Create a historical record if not found (robustness for demo)
        pending_intervention = Intervention(
            user_id=user.id,
            session_id=request.session_id,
            feature_name=request.feature_name,
            gap_type="Confidence Gap",
            dcs_at_intervention=user.current_dcs,
            mode_triggered=request.mode,
            message_delivered="",
            timestamp=datetime.utcnow()
        )
        db.add(pending_intervention)

    pending_intervention.outcome = request.outcome
    pending_intervention.resolved_at = datetime.utcnow()
    db.commit()

    # Log positive behavior to telemetry if completed
    if request.outcome == "completed":
        completed_event = SessionTelemetry(
            user_id=user.id,
            session_id=request.session_id,
            feature_name=request.feature_name,
            action="complete",
            dwell_time=0.0,
            timestamp=datetime.utcnow()
        )
        db.add(completed_event)
        db.commit()

    # Recalculate DCS (so completing interventions immediately bumps the DCS score)
    user = update_user_dcs(db, user)

    return {
        "status": "success",
        "new_dcs": user.current_dcs,
        "new_dcs_band": user.current_dcs_band
    }

@app.get("/api/dashboard/metrics")
def get_dashboard_metrics(db: Session = Depends(get_db)):
    users = db.query(User).all()
    if not users:
        return {}
    
    total_users = len(users)
    avg_dcs = sum([u.current_dcs for u in users]) / total_users
    
    bands = {"Dormant": 0, "Cautious": 0, "Developing": 0, "Confident": 0, "Advocate": 0}
    for u in users:
        bands[u.current_dcs_band] = bands.get(u.current_dcs_band, 0) + 1
        
    interventions = db.query(Intervention).all()
    total_int = len(interventions)
    completed_int = len([i for i in interventions if i.outcome == 'completed'])
    dismissed_int = len([i for i in interventions if i.outcome == 'dismissed'])
    
    # Calculate conversion uplift rate
    # Percentage of Mode 2 walkthroughs that completed vs dismissed
    mode_2_runs = [i for i in interventions if i.mode_triggered == 2]
    total_mode_2 = len(mode_2_runs)
    completed_mode_2 = len([i for i in mode_2_runs if i.outcome == 'completed'])
    walkthrough_success_rate = (completed_mode_2 / total_mode_2 * 100.0) if total_mode_2 > 0 else 0.0

    # Counts of friction types classified
    gaps = {"Awareness Gap": 0, "Confidence Gap": 0, "Access Gap": 0, "Language Gap": 0}
    for i in interventions:
        if i.gap_type in gaps:
            gaps[i.gap_type] += 1

    # Staff Queue Counts
    staff_pending = db.query(StaffQueue).filter(StaffQueue.status == 'pending').count()
    staff_resolved = db.query(StaffQueue).filter(StaffQueue.status == 'resolved').count()

    # Retraining Queue: simulate pending logs for learning loop
    pending_retrain_count = len([i for i in interventions if i.outcome != "pending"])
    
    return {
        "total_users": total_users,
        "avg_dcs": round(avg_dcs, 1),
        "bands_distribution": {
            "Dormant": round(bands["Dormant"] / total_users * 100.0, 1),
            "Cautious": round(bands["Cautious"] / total_users * 100.0, 1),
            "Developing": round(bands["Developing"] / total_users * 100.0, 1),
            "Confident": round(bands["Confident"] / total_users * 100.0, 1),
            "Advocate": round(bands["Advocate"] / total_users * 100.0, 1),
        },
        "interventions": {
            "total": total_int,
            "completed": completed_int,
            "dismissed": dismissed_int,
            "walkthrough_success_rate": round(walkthrough_success_rate, 1)
        },
        "friction_distribution": gaps,
        "staff_queue": {
            "pending": staff_pending,
            "resolved": staff_resolved
        },
        "pending_retrain_count": pending_retrain_count
    }

@app.get("/api/dashboard/staff/queue", response_model=List[StaffQueueItem])
def get_staff_queue(db: Session = Depends(get_db)):
    queue = db.query(StaffQueue).order_by(StaffQueue.escalated_at.desc()).all()
    result = []
    for item in queue:
        result.append(StaffQueueItem(
            id=item.id,
            account_number=item.user.account_number,
            customer_name=item.user.name,
            primary_language=item.user.primary_language,
            escalated_at=item.escalated_at.strftime("%Y-%m-%d %H:%M:%S"),
            feature_name=item.feature_name,
            reason_code=item.reason_code,
            context_summary=item.context_summary,
            status=item.status
        ))
    return result

@app.post("/api/dashboard/staff/update")
def update_staff_status(
    queue_id: int = Query(...), 
    status: str = Query(...), 
    notes: str = Query(None), 
    db: Session = Depends(get_db)
):
    item = db.query(StaffQueue).filter(StaffQueue.id == queue_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    item.status = status
    if notes:
        item.executive_notes = notes
    db.commit()
    return {"status": "success"}

@app.post("/api/reset")
def reset_database(db: Session = Depends(get_db)):
    # Clean up everything and regenerate
    db.query(StaffQueue).delete()
    db.query(Intervention).delete()
    db.query(SessionTelemetry).delete()
    db.query(User).delete()
    db.commit()
    generate_synthetic_data(db, 100)
    return {"status": "success", "message": "Database reset and seeded successfully."}
