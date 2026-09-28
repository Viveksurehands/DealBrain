"""
Hindsight Data Models & Schema Definitions
Defines strict data structures for enterprise deal intelligence with historical traceability.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime
import uuid

@dataclass
class SentimentPoint:
    date: str
    sentiment: str  # positive, neutral, skeptical, negative, champion
    notes: Optional[str] = None

@dataclass
class Stakeholder:
    contact_id: str
    name: str
    role: str
    influence_level: str = "medium"  # low, medium, high, decision_maker, champion
    current_sentiment: str = "neutral"
    sentiment_history: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class Objection:
    objection_id: str
    category: str  # pricing, technical, competitive, timing, security
    objection_text: str
    handling_attempted: Optional[str] = None
    resolved: bool = False
    date_raised: str = ""
    interaction_id: Optional[str] = None

@dataclass
class CompetitorMention:
    mention_id: str
    competitor_name: str
    context: str
    comparative_angle_used: Optional[str] = None
    threat_level: str = "medium"  # low, medium, high
    interaction_id: Optional[str] = None
    date_mentioned: str = ""

@dataclass
class Commitment:
    commitment_id: str
    owner: str  # e.g., "rep", "prospect", or specific name
    description: str
    due_date: Optional[str] = None
    status: str = "open"  # open, fulfilled, breached, cancelled
    interaction_id: Optional[str] = None
    date_created: str = ""

@dataclass
class Interaction:
    interaction_id: str
    account_id: str
    interaction_date: str
    interaction_type: str  # call, email, meeting, demo, negotiation
    summary: str
    stakeholders_present: List[str] = field(default_factory=list)  # contact_ids or names
    objection_ids: List[str] = field(default_factory=list)
    competitor_mention_ids: List[str] = field(default_factory=list)
    commitment_ids: List[str] = field(default_factory=list)
    deal_stage_signal: Optional[str] = None
    raw_notes_excerpt: Optional[str] = None

@dataclass
class Account:
    account_id: str
    company_name: str
    industry: Optional[str] = None
    arr_estimate: Optional[float] = None
    current_stage: str = "Discovery"  # Discovery, Demo, Technical Evaluation, Proposal/Negotiation, Closed-Won, Closed-Lost
    status: str = "active"  # active, won, lost, stalled
    last_activity_date: Optional[str] = None
    champion_id: Optional[str] = None
    economic_buyer_id: Optional[str] = None
    created_at: str = ""
    stakeholders: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    objections: List[Dict[str, Any]] = field(default_factory=list)
    competitors: List[Dict[str, Any]] = field(default_factory=list)
    commitments: List[Dict[str, Any]] = field(default_factory=list)
    interaction_history: List[Dict[str, Any]] = field(default_factory=list)
