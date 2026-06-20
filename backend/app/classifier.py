from sqlalchemy.orm import Session
from backend.app.database import SessionTelemetry, User

def classify_friction(db: Session, user: User, session_id: str, current_feature: str) -> tuple[str | None, float, str]:
    """
    Classifies behavioral friction into Awareness, Confidence, Access, or Language gaps.
    Returns: (gap_type, classifier_confidence, explainable_rule_path)
    """
    # 1. Fetch telemetry for the current active session
    session_telemetry = db.query(SessionTelemetry).filter(
        SessionTelemetry.user_id == user.id,
        SessionTelemetry.session_id == session_id
    ).all()
    
    # 2. Fetch historical telemetry for this feature
    history_feature = db.query(SessionTelemetry).filter(
        SessionTelemetry.user_id == user.id,
        SessionTelemetry.feature_name == current_feature
    ).all()

    # Calculate some helper features
    total_visits = len([e for e in history_feature if e.action == 'visit'])
    total_completions = len([e for e in history_feature if e.action == 'complete'])
    total_errors = len([e for e in session_telemetry if e.error_occurred])
    
    # Current event details
    current_events = [e for e in session_telemetry if e.feature_name == current_feature]
    current_dwell = sum([e.dwell_time for e in current_events if e.action == 'dwell'])
    current_errors = len([e for e in current_events if e.error_occurred])
    
    # Check for rapid back-navigation (multiple visits of very short duration < 4s)
    short_visits = len([e for e in session_telemetry if e.action == 'visit' and e.dwell_time < 4.0])
    
    # Calculate streak of repeat tasks (checking balance or basic UPI repeatedly)
    # Let's count how many times they visited only 'balance_check' or 'upi_transfer' in the last 15 actions
    recent_telemetry = db.query(SessionTelemetry).filter(
        SessionTelemetry.user_id == user.id
    ).order_by(SessionTelemetry.timestamp.desc()).limit(15).all()
    
    repeat_task_streak = 0
    for e in recent_telemetry:
        if e.feature_name in ['balance_check', 'upi_transfer']:
            repeat_task_streak += 1
        else:
            break

    # Rule 1: Technical / Access Gap (highest priority)
    if current_errors > 0 or total_errors > 1:
        error_msg = next((e.error_message for e in current_events if e.error_occurred and e.error_message), "Technical error")
        rule_path = f"Error Flag Detected -> Current Session Errors ({current_errors}) > 0 OR Historical Errors ({total_errors}) > 1 -> Access Gap (Reason: {error_msg})"
        return "Access Gap", 0.95, rule_path

    # Rule 2: Language Gap
    # If the user has short sessions, rapid back-navigations, and their primary language is non-English,
    # or they show high short-visit count, it suggests UI comprehension failure.
    if short_visits >= 3 and user.primary_language != "en":
        rule_path = f"Short Visit Count ({short_visits}) >= 3 -> User Language is '{user.primary_language}' -> Language Comprehension Friction -> Language Gap"
        return "Language Gap", 0.85, rule_path

    # Rule 3: Confidence Gap
    # User has visited the feature before (>= 1 times), spent significant dwell time (e.g. > 15s in this session),
    # but has never completed a transaction in this feature.
    if total_visits >= 2 and total_completions == 0 and current_dwell > 15.0:
        rule_path = f"Visits ({total_visits}) >= 2 -> Completions == 0 -> Current Session Dwell Time ({current_dwell}s) > 15s -> Confidence Gap"
        return "Confidence Gap", 0.90, rule_path

    # Rule 4: Awareness Gap
    # User has never visited this feature, or has high repeat task streak and has visited it 0 times historically
    if total_visits == 0 and repeat_task_streak >= 5:
        rule_path = f"Feature Visits == 0 -> Repeat Basic Task Streak ({repeat_task_streak}) >= 5 -> Undiscovered Feature -> Awareness Gap"
        return "Awareness Gap", 0.80, rule_path

    # Secondary check: if they've never visited this feature and just opened it
    if total_visits <= 1 and total_completions == 0:
        # Just opened it, maybe let them explore. But if their DCS is Dormant, we nudged them
        if user.current_dcs_band == "Dormant":
            rule_path = f"DCS Band is Dormant -> Feature Visits ({total_visits}) <= 1 -> Proactive Discovery Nudge -> Awareness Gap"
            return "Awareness Gap", 0.75, rule_path

    return None, 0.0, "No behavioral friction detected."
