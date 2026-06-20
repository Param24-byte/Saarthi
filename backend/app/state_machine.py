from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.app.database import Intervention, StaffQueue, User

def get_next_intervention_mode(
    db: Session, 
    user: User, 
    session_id: str, 
    gap_type: str | None, 
    feature_name: str
) -> tuple[int, str]:
    """
    Decides the next intervention mode using DCS, Gap Type, and historical outcomes.
    Returns: (mode, message)
    """
    dcs = user.current_dcs
    band = user.current_dcs_band

    # If no gap is classified, do not intervene
    if not gap_type:
        return 0, "No intervention needed."

    # 1. Frequency check: check if we already intervened in this session
    session_interventions = db.query(Intervention).filter(
        Intervention.user_id == user.id,
        Intervention.session_id == session_id
    ).all()
    
    if len(session_interventions) >= 1:
        # Frequency Cap: Max 1 intervention per session (to prevent notification fatigue)
        return 0, "Frequency cap reached: Max 1 intervention per session."

    # 2. Check for Access Gap -> Immediate Mode 4 Escalation
    if gap_type == "Access Gap":
        # Check if already escalated for this feature to avoid duplicates
        existing_escalation = db.query(StaffQueue).filter(
            StaffQueue.user_id == user.id,
            StaffQueue.feature_name == feature_name,
            StaffQueue.status == "pending"
        ).first()
        
        if not existing_escalation:
            queue_entry = StaffQueue(
                user_id=user.id,
                feature_name=feature_name,
                reason_code="ACCESS_ERR",
                context_summary=f"Technical blockage/error detected in {feature_name} page for customer using YONO app.",
                status="pending"
            )
            db.add(queue_entry)
            db.commit()
            
        return 4, f"Technical issue detected on {feature_name}. Support request raised with branch staff."

    # 3. Dismissal counts: Count dismissals of BFI nudges on this feature in the last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_dismissals = db.query(Intervention).filter(
        Intervention.user_id == user.id,
        Intervention.feature_name == feature_name,
        Intervention.outcome == "dismissed",
        Intervention.timestamp >= seven_days_ago
    ).count()

    # Mode 3 Backoff / Silence rule:
    # If the user dismissed interventions on this feature twice, we enter Mode 3 (Silence)
    if recent_dismissals >= 2:
        # If the user is in Cautious or Dormant band, we escalate to staff (Mode 4) for high-value triage,
        # otherwise we just stay silent (Mode 3 backoff)
        if band in ["Dormant", "Cautious"]:
            existing_esc = db.query(StaffQueue).filter(
                StaffQueue.user_id == user.id,
                StaffQueue.feature_name == feature_name,
                StaffQueue.status == "pending"
            ).first()
            if not existing_esc:
                queue_entry = StaffQueue(
                    user_id=user.id,
                    feature_name=feature_name,
                    reason_code="MULTIPLE_DISMISSALS",
                    context_summary=f"User in {band} band dismissed voice/card assistance twice on {feature_name}. Escalate for human support callback.",
                    status="pending"
                )
                db.add(queue_entry)
                db.commit()
            return 4, f"Assistance dismissed twice. User queued for staff callback."
        else:
            return 3, "Mode 3 Backoff active: Silence mode to prevent notification fatigue."

    # 4. Check if Mode 2 voice walkthrough has triggered for this feature in the past 30 days
    # Walkthroughs should be rare and high-impact
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_voice_runs = db.query(Intervention).filter(
        Intervention.user_id == user.id,
        Intervention.feature_name == feature_name,
        Intervention.mode_triggered == 2,
        Intervention.timestamp >= thirty_days_ago
    ).count()

    # 5. Core Mapping based on Gap Type and DCS Band
    # Awareness Gap
    if gap_type == "Awareness Gap":
        if band in ["Dormant", "Cautious", "Developing"]:
            msg = get_intervention_message("Awareness Gap", feature_name, user.primary_language)
            return 1, msg
        else:
            return 0, "Awareness gap ignored for high-DCS user."

    # Language Gap
    elif gap_type == "Language Gap":
        # Triggers a voice walkthrough in preferred language
        if recent_voice_runs == 0:
            msg = get_intervention_message("Language Gap", feature_name, user.primary_language)
            return 2, msg
        else:
            return 0, "Language gap voice guide suppressed by 30-day frequency cap."

    # Confidence Gap
    elif gap_type == "Confidence Gap":
        if band in ["Dormant", "Cautious", "Developing"]:
            if recent_voice_runs == 0:
                msg = get_intervention_message("Confidence Gap", feature_name, user.primary_language)
                return 2, msg
            else:
                # Fallback to Mode 1 card if Mode 2 is on cooldown
                msg = f"Need help with {feature_name.replace('_', ' ').title()}? Open a voice guide anytime."
                return 1, msg
        else:
            return 0, "Confidence gap ignored for high-DCS user."

    return 0, "No intervention mapping matched."

def get_intervention_message(gap_type: str, feature: str, lang: str) -> str:
    feature_clean = feature.replace("_", " ").title()
    
    # Translations (English, Hindi, Tamil)
    messages = {
        "Awareness Gap": {
            "en": f"Did you know? You can now open a {feature_clean} online in 2 minutes. Try it now!",
            "hi": f"क्या आप जानते हैं? अब आप 2 मिनट में ऑनलाइन {feature_clean} खोल सकते हैं। अभी प्रयास करें!",
            "ta": f"உங்களுக்குத் தெரியுமா? நீங்கள் இப்போது 2 நிமிடங்களில் ஆன்லைனில் {feature_clean}-ஐத் தொடங்கலாம். இப்போது முயற்சிக்கவும்!"
        },
        "Confidence Gap": {
            "en": f"Let's complete your {feature_clean} together. Tap to start our voice walkthrough guide.",
            "hi": f"आइए मिलकर आपकी {feature_clean} प्रक्रिया पूरी करें। हमारी वॉयस गाइड शुरू करने के लिए टैप करें।",
            "ta": f"உங்களது {feature_clean} பரிவர்த்தனையை ஒன்றாக முடிப்போம். எங்கள் குரல் வழிகாட்டியைத் தொடங்க தட்டவும்."
        },
        "Language Gap": {
            "en": f"Interface language feels difficult? Tap to switch to a voice guide in your preferred language.",
            "hi": f"क्या भाषा समझने में कठिनाई हो रही है? अपनी पसंदीदा भाषा में वॉयस गाइड पर जाने के लिए टैप करें।",
            "ta": f"மொழி கடினமாக உள்ளதா? உங்களுக்கு விருப்பமான மொழியில் குரல் வழிகாட்டிக்கு மாற தட்டவும்."
        }
    }
    
    lang_key = lang if lang in ["en", "hi", "ta"] else "en"
    return messages[gap_type].get(lang_key, messages[gap_type]["en"])
