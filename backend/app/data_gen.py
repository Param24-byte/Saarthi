import random
import uuid
from datetime import datetime, timedelta
from faker import Faker
from sqlalchemy.orm import Session
from backend.app.database import init_db, SessionLocal, User, SessionTelemetry, Intervention, StaffQueue
from backend.app.dcs_calculator import calculate_user_dcs, get_dcs_band

fake = Faker('en_IN')

# Target features
FEATURES = ['balance_check', 'upi_transfer', 'recurring_deposit', 'mutual_funds', 'insurance']

def generate_synthetic_data(db: Session, num_users: int = 100):
    # Check if we already have users
    if db.query(User).count() > 0:
        print("Database already has data. Skipping generation.")
        return

    print(f"Generating synthetic telemetry for {num_users} users...")
    
    # 1. Create Users
    users = []
    languages = ['en', 'hi', 'ta']
    
    # Cohorts distribution:
    # 20 Confident/Advocate
    # 35 Cautious
    # 30 Dormant
    # 10 Language Gap
    # 5 Access Gap
    
    for i in range(num_users):
        name = fake.name()
        # SBI style account number
        account_number = f"30{random.randint(100000000, 999999999)}"
        
        # Assign language based on cohort
        if i >= 80 and i < 90:
            lang = random.choice(['hi', 'ta']) # Language gap cohort preferred languages
        else:
            lang = random.choice(languages)
            
        registered_date = datetime.utcnow() - timedelta(days=random.randint(30, 90))
        
        user = User(
            account_number=account_number,
            name=name,
            primary_language=lang,
            registered_at=registered_date,
            current_dcs=50.0, # Will update after telemetry
            current_dcs_band="Developing"
        )
        db.add(user)
        users.append((i, user))
        
    db.commit()

    # 2. Generate Telemetry for each User
    for idx, user in users:
        # Number of sessions: 5 to 15
        num_sessions = random.randint(5, 15)
        
        # Cohorts categorization:
        # A. Confident / Advocate (0 - 19)
        # B. Cautious (20 - 54)
        # C. Dormant (55 - 84)
        # D. Language Gap (85 - 94)
        # E. Access Gap (95 - 99)
        
        for sess_idx in range(num_sessions):
            session_id = str(uuid.uuid4())
            session_start = user.registered_at + timedelta(days=sess_idx * 3, hours=random.randint(1, 12))
            
            # Scenario A: Confident / Advocate
            if idx < 20:
                # Performs balance checks, UPI transfers, and occasionally RD or Mutual funds with high completion rates
                visited_features = random.sample(FEATURES, k=random.randint(2, 4))
                for f_name in visited_features:
                    # Visit event
                    db.add(SessionTelemetry(
                        user_id=user.id,
                        session_id=session_id,
                        timestamp=session_start,
                        feature_name=f_name,
                        action='visit',
                        dwell_time=random.uniform(2.0, 5.0)
                    ))
                    # Attempt & Completion for transacting features
                    if f_name in ['upi_transfer', 'recurring_deposit', 'mutual_funds']:
                        db.add(SessionTelemetry(
                            user_id=user.id,
                            session_id=session_id,
                            timestamp=session_start + timedelta(seconds=10),
                            feature_name=f_name,
                            action='attempt'
                        ))
                        db.add(SessionTelemetry(
                            user_id=user.id,
                            session_id=session_id,
                            timestamp=session_start + timedelta(seconds=20),
                            feature_name=f_name,
                            action='complete'
                        ))
            
            # Scenario B: Cautious
            elif 20 <= idx < 55:
                # Visits balance check and UPI.
                # Attempts RD or Mutual funds, spends high dwell time, but exits without completion.
                # Balance check (regularly completed)
                db.add(SessionTelemetry(
                    user_id=user.id,
                    session_id=session_id,
                    timestamp=session_start,
                    feature_name='balance_check',
                    action='visit',
                    dwell_time=random.uniform(3.0, 6.0)
                ))
                
                # Check Recurring Deposit or Mutual Funds (abandonment)
                hesitate_feature = 'recurring_deposit' if idx % 2 == 0 else 'mutual_funds'
                
                # Visited multiple times
                db.add(SessionTelemetry(
                    user_id=user.id,
                    session_id=session_id,
                    timestamp=session_start + timedelta(seconds=15),
                    feature_name=hesitate_feature,
                    action='visit',
                    dwell_time=random.uniform(18.0, 35.0) # High dwell time!
                ))
                # Exits without doing anything
                db.add(SessionTelemetry(
                    user_id=user.id,
                    session_id=session_id,
                    timestamp=session_start + timedelta(seconds=50),
                    feature_name=hesitate_feature,
                    action='exit_without_action',
                    dwell_time=0.0
                ))
                
                # Sometime triggers intervention (logged historically)
                if sess_idx > 3 and random.random() > 0.4:
                    outcome = random.choice(['completed', 'dismissed', 'ignored'])
                    mode = 2 # Voice
                    db.add(Intervention(
                        user_id=user.id,
                        session_id=session_id,
                        timestamp=session_start + timedelta(seconds=30),
                        feature_name=hesitate_feature,
                        gap_type='Confidence Gap',
                        dcs_at_intervention=35.0,
                        mode_triggered=mode,
                        message_delivered=f"Need help? Let's walk through {hesitate_feature.replace('_', ' ').title()} together.",
                        outcome=outcome
                    ))
                    
                    if outcome == 'completed':
                        db.add(SessionTelemetry(
                            user_id=user.id,
                            session_id=session_id,
                            timestamp=session_start + timedelta(seconds=60),
                            feature_name=hesitate_feature,
                            action='complete'
                        ))

            # Scenario C: Dormant
            elif 55 <= idx < 85:
                # Exclusively uses balance check and UPI.
                # Never visits RD, Mutual Funds, or Insurance.
                db.add(SessionTelemetry(
                    user_id=user.id,
                    session_id=session_id,
                    timestamp=session_start,
                    feature_name='balance_check',
                    action='visit',
                    dwell_time=random.uniform(2.0, 5.0)
                ))
                if random.random() > 0.3:
                    db.add(SessionTelemetry(
                        user_id=user.id,
                        session_id=session_id,
                        timestamp=session_start + timedelta(seconds=5),
                        feature_name='upi_transfer',
                        action='visit',
                        dwell_time=random.uniform(4.0, 8.0)
                    ))
                    db.add(SessionTelemetry(
                        user_id=user.id,
                        session_id=session_id,
                        timestamp=session_start + timedelta(seconds=15),
                        feature_name='upi_transfer',
                        action='complete'
                    ))

            # Scenario D: Language Gap
            elif 85 <= idx < 95:
                # Rapid back-navigations. Visits a screen, exits within 2-3 seconds, repeats.
                lang_feature = 'insurance' if idx % 2 == 0 else 'mutual_funds'
                
                # Rapid visits
                for r in range(3):
                    db.add(SessionTelemetry(
                        user_id=user.id,
                        session_id=session_id,
                        timestamp=session_start + timedelta(seconds=r * 15),
                        feature_name=lang_feature,
                        action='visit',
                        dwell_time=random.uniform(1.0, 3.5) # Short dwell time
                    ))
                    db.add(SessionTelemetry(
                        user_id=user.id,
                        session_id=session_id,
                        timestamp=session_start + timedelta(seconds=r * 15 + 4),
                        feature_name=lang_feature,
                        action='exit_without_action'
                    ))
                    
                # Log a language gap intervention
                if sess_idx > 2:
                    db.add(Intervention(
                        user_id=user.id,
                        session_id=session_id,
                        timestamp=session_start + timedelta(seconds=20),
                        feature_name=lang_feature,
                        gap_type='Language Gap',
                        dcs_at_intervention=42.0,
                        mode_triggered=2, # Voice
                        message_delivered=f"Interface language feels difficult? Tap to switch to voice guidance.",
                        outcome='dismissed'
                    ))

            # Scenario E: Access Gap (Technical)
            else:
                # Attempting something but getting errors
                err_feature = 'insurance' if idx % 2 == 0 else 'recurring_deposit'
                
                db.add(SessionTelemetry(
                    user_id=user.id,
                    session_id=session_id,
                    timestamp=session_start,
                    feature_name=err_feature,
                    action='visit',
                    dwell_time=random.uniform(5.0, 10.0)
                ))
                db.add(SessionTelemetry(
                    user_id=user.id,
                    session_id=session_id,
                    timestamp=session_start + timedelta(seconds=12),
                    feature_name=err_feature,
                    action='attempt'
                ))
                
                # Error event!
                db.add(SessionTelemetry(
                    user_id=user.id,
                    session_id=session_id,
                    timestamp=session_start + timedelta(seconds=15),
                    feature_name=err_feature,
                    action='exit_without_action',
                    error_occurred=True,
                    error_message='RBI KYC validation failed (PAN card not verified)'
                ))
                
                # Escalate to queue automatically
                if sess_idx > 1:
                    db.add(StaffQueue(
                        user_id=user.id,
                        feature_name=err_feature,
                        reason_code='ACCESS_ERR',
                        context_summary=f"RBI KYC validation failed (PAN card not verified) for customer {user.name} on feature {err_feature}.",
                        status='pending'
                    ))

    db.commit()

    # 3. Compute final DCS for all users and save
    print("Recalculating DCS scores for synthetic users...")
    all_users = db.query(User).all()
    for user in all_users:
        score, _ = calculate_user_dcs(db, user.id)
        user.current_dcs = score
        user.current_dcs_band = get_dcs_band(score)
        
    db.commit()
    print("Synthetic data generation complete!")

if __name__ == "__main__":
    db = SessionLocal()
    init_db()
    generate_synthetic_data(db, 100)
    db.close()
