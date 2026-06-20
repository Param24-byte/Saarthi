from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.app.database import SessionTelemetry, User

ALL_FEATURES = ['balance_check', 'upi_transfer', 'recurring_deposit', 'mutual_funds', 'insurance']

def get_dcs_band(score: float) -> str:
    if score <= 20.0:
        return "Dormant"
    elif score <= 45.0:
        return "Cautious"
    elif score <= 70.0:
        return "Developing"
    elif score <= 90.0:
        return "Confident"
    else:
        return "Advocate"

def calculate_user_dcs(db: Session, user_id: int) -> tuple[float, dict]:
    # Query all telemetry for this user
    telemetry = db.query(SessionTelemetry).filter(SessionTelemetry.user_id == user_id).all()
    
    if not telemetry:
        # Default baseline for a brand new user
        default_breakdown = {
            "feature_breadth": 20.0,  # knows balance check
            "completion_rate": 50.0,
            "hesitation_decay": 80.0,
            "return_rate": 50.0
        }
        return 45.0, default_breakdown

    # 1. Feature Breadth (30%)
    # Ratio of unique features attempted/completed vs total features
    attempted_features = set()
    for event in telemetry:
        if event.action in ['attempt', 'complete']:
            attempted_features.add(event.feature_name)
    
    feature_breadth_score = (len(attempted_features) / len(ALL_FEATURES)) * 100.0
    
    # 2. Completion Rate (30%)
    # Transactions completed / transactions attempted or visited
    # Features requiring completion: upi_transfer, recurring_deposit, mutual_funds, insurance
    features_requiring_completion = ['upi_transfer', 'recurring_deposit', 'mutual_funds', 'insurance']
    
    sessions_initiated = set()
    sessions_completed = set()
    
    for event in telemetry:
        if event.feature_name in features_requiring_completion:
            if event.action == 'visit':
                sessions_initiated.add((event.session_id, event.feature_name))
            elif event.action == 'complete':
                sessions_completed.add((event.session_id, event.feature_name))
                
    # Ensure completed sessions count as initiated even if clickstream visit was missed
    sessions_initiated.update(sessions_completed)
    
    if len(sessions_initiated) > 0:
        completion_rate = (len(sessions_completed) / len(sessions_initiated)) * 100.0
    else:
        completion_rate = 50.0 # default baseline
        
    # 3. Hesitation Decay Index (25%)
    # Inverse of (dwell-then-exit events / total feature visits)
    # A dwell-then-exit event: user spent > 15 seconds on a page but action was 'exit_without_action' or 'dismiss'
    visits = 0
    hesitations = 0
    
    for event in telemetry:
        if event.action == 'visit':
            visits += 1
        elif event.action in ['exit_without_action', 'dismiss']:
            if event.dwell_time > 15.0:
                hesitations += 1
                
    if visits > 0:
        hesitation_ratio = hesitations / visits
        hesitation_decay = (1.0 - hesitation_ratio) * 100.0
    else:
        hesitation_decay = 80.0 # default baseline

    # 4. Return Rate (15%)
    # Number of times a user returned to a feature within 7 days of abandoning it
    abandoned_events = [] # list of (timestamp, feature_name)
    return_counts = 0
    
    # Find all abandonments
    for event in telemetry:
        if event.action in ['exit_without_action', 'dismiss']:
            abandoned_events.append((event.timestamp, event.feature_name))
            
    # Check if user returned to those features within 7 days
    for ab_time, ab_feat in abandoned_events:
        returned = False
        for event in telemetry:
            if event.feature_name == ab_feat and event.timestamp > ab_time:
                if event.timestamp <= ab_time + timedelta(days=7):
                    if event.action in ['visit', 'attempt', 'complete']:
                        returned = True
                        break
        if returned:
            return_counts += 1
            
    if len(abandoned_events) > 0:
        return_rate = (return_counts / len(abandoned_events)) * 100.0
    else:
        return_rate = 100.0 # no abandonments means they return/stay, or didn't drop

    # Composite Score Calculation
    score = (
        (0.30 * feature_breadth_score) +
        (0.30 * completion_rate) +
        (0.25 * hesitation_decay) +
        (0.15 * return_rate)
    )
    
    # Bound the score to [0.0, 100.0]
    score = max(0.0, min(100.0, round(score, 1)))
    
    breakdown = {
        "feature_breadth": round(feature_breadth_score, 1),
        "completion_rate": round(completion_rate, 1),
        "hesitation_decay": round(hesitation_decay, 1),
        "return_rate": round(return_rate, 1)
    }
    
    return score, breakdown

def update_user_dcs(db: Session, user: User) -> User:
    score, _ = calculate_user_dcs(db, user.id)
    user.current_dcs = score
    user.current_dcs_band = get_dcs_band(score)
    db.commit()
    db.refresh(user)
    return user
