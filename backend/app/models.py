from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class TelemetryEvent(BaseModel):
    account_number: str
    session_id: str
    feature_name: str
    action: str  # 'visit', 'dwell', 'attempt', 'complete', 'dismiss', 'exit_without_action'
    dwell_time: Optional[float] = 0.0
    error_occurred: Optional[bool] = False
    error_message: Optional[str] = None

class InterventionResponse(BaseModel):
    should_intervene: bool
    mode: int  # 0: None, 1: Contextual Nudge, 2: Voice Walkthrough, 3: Backoff, 4: Escalation
    gap_type: Optional[str] = None  # 'Awareness', 'Confidence', 'Access', 'Language'
    message: Optional[str] = None
    language: Optional[str] = None
    target_feature: Optional[str] = None
    dcs: float
    current_dcs_band: str

class OutcomeRequest(BaseModel):
    account_number: str
    session_id: str
    feature_name: str
    mode: int
    outcome: str  # 'completed', 'dismissed', 'ignored'

class StaffQueueItem(BaseModel):
    id: int
    account_number: str
    customer_name: str
    primary_language: str
    escalated_at: str
    feature_name: str
    reason_code: str
    context_summary: str
    status: str

class DCSComponentBreakdown(BaseModel):
    feature_breadth: float
    completion_rate: float
    hesitation_decay: float
    return_rate: float

class UserProfileResponse(BaseModel):
    account_number: str
    name: str
    primary_language: str
    current_dcs: float
    current_dcs_band: str
    components: DCSComponentBreakdown

class ROIResponse(BaseModel):
    revenue_uplift_cr: float
    staff_hours_saved: float
    notification_reduction_pct: float
