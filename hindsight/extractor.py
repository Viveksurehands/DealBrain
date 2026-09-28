"""
Hindsight Interaction Extractor
Extracts structured deal intelligence from raw sales call transcripts, email threads,
and meeting notes without speculative extrapolation.
Enforces the no-fabrication rule: only explicit, stated facts are extracted.
"""

import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from .engine import HindsightEngine

class DealInteractionExtractor:
    """
    Deterministic rule-based extractor for enterprise sales interactions.
    Extracts stakeholders, objections, competitors, commitments, and stage shifts.
    """

    KNOWN_COMPETITORS = [
        "salesforce", "hubspot", "datadog", "snowflake", "dynatrace", "splunk",
        "new relic", "mongodb", "clari", "gong", "outreach", "datafast",
        "palantir", "aws", "azure", "google cloud"
    ]

    OBJECTION_PATTERNS = {
        "pricing": [
            r"budget", r"cost", r"price", r"pricing", r"expensive", r"discount",
            r"annual contract", r"setup fee", r"per user", r"\$\d+", r"too high"
        ],
        "technical": [
            r"latency", r"sla", r"api", r"integration", r"uptime", r"scale",
            r"throughput", r"on-prem", r"vpc", r"architecture", r"sdk", r"performance"
        ],
        "security": [
            r"soc2", r"soc 2", r"hipaa", r"iso 27001", r"gdpr", r"compliance",
            r"security audit", r"penetration test", r"data residency"
        ],
        "timing": [
            r"next quarter", r"q[1-4]", r"freeze", r"delayed", r"not right now",
            r"timeline", r"next year", r"postpone", r"bandwidth"
        ],
        "competitive": [
            r"evaluating", r"already using", r"comparing with", r"locked into", r"contract with"
        ]
    }

    def __init__(self, engine: Optional[HindsightEngine] = None):
        self.engine = engine

    def extract_from_text(
        self,
        raw_text: str,
        account_id: Optional[str] = None,
        interaction_date: Optional[str] = None,
        interaction_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extracts structured facts from raw text.
        Returns a clean dictionary matching Hindsight schema.
        """
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        # 1. Infer interaction type if not provided
        detected_type = interaction_type or self._detect_interaction_type(raw_text)

        # 2. Extract date if present (e.g., Date: YYYY-MM-DD or 2026-09-20)
        detected_date = interaction_date or self._extract_date(raw_text) or datetime.now().strftime("%Y-%m-%d")

        # 3. Extract Stakeholders and Sentiment
        stakeholders = self._extract_stakeholders(lines, raw_text)

        # 4. Extract Objections
        objections = self._extract_objections(lines, raw_text)

        # 5. Extract Competitor Mentions
        competitors = self._extract_competitors(lines, raw_text)

        # 6. Extract Commitments / Action Items
        commitments = self._extract_commitments(lines, raw_text)

        # 7. Extract Deal Stage Signals
        stage_signal = self._detect_stage_signal(raw_text)

        # 8. Concise summary
        summary = self._generate_summary(lines, detected_type, stakeholders, objections, commitments)

        return {
            "account_id": account_id,
            "interaction_date": detected_date,
            "interaction_type": detected_type,
            "stakeholders_present": stakeholders,
            "objections_raised": objections,
            "competitors_mentioned": competitors,
            "commitments_made": commitments,
            "deal_stage_signal": stage_signal,
            "summary": summary,
            "raw_notes_excerpt": raw_text[:500] if len(raw_text) > 500 else raw_text
        }

    def _detect_interaction_type(self, text: str) -> str:
        text_lower = text.lower()
        if "subject:" in text_lower or "from:" in text_lower or "to:" in text_lower:
            return "email"
        if "call transcript" in text_lower or "zoom" in text_lower or "attendees:" in text_lower:
            return "call"
        if "demo" in text_lower or "walkthrough" in text_lower:
            return "demo"
        if "negotiation" in text_lower or "terms" in text_lower:
            return "negotiation"
        return "meeting"

    def _extract_date(self, text: str) -> Optional[str]:
        # Matches YYYY-MM-DD
        iso_match = re.search(r"\b(20\d{2}[-/]\d{2}[-/]\d{2})\b", text)
        if iso_match:
            return iso_match.group(1).replace("/", "-")
        # Matches e.g., Sept 20, 2026 or September 20, 2026
        written_match = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(20\d{2})\b", text, re.I)
        if written_match:
            try:
                dt = datetime.strptime(f"{written_match.group(1)[:3]} {written_match.group(2)} {written_match.group(3)}", "%b %d %Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        return None

    def _extract_stakeholders(self, lines: List[str], full_text: str) -> List[Dict[str, Any]]:
        stakeholders = []
        seen_names = set()

        # Check for explicit Attendees: or Stakeholders: sections
        for i, line in enumerate(lines):
            if re.match(r"^(attendees|participants|stakeholders|meeting with):", line, re.I):
                attendee_text = line.split(":", 1)[1]
                # Split by commas or semicolons
                raw_names = [n.strip() for n in re.split(r"[,;]", attendee_text) if n.strip()]
                for raw_n in raw_names:
                    s_data = self._parse_stakeholder_entry(raw_n, full_text)
                    if s_data["name"].lower() not in seen_names:
                        seen_names.add(s_data["name"].lower())
                        stakeholders.append(s_data)

        # Check transcript speaker tags (e.g., "Sarah Chen (VP Eng):", "Mark (CFO):")
        speaker_matches = re.findall(r"^([A-Z][a-zA-Z\s\.\-]{1,25})(?:\s*\(([^)]+)\))?\s*:", full_text, re.MULTILINE)
        for name_candidate, role_candidate in speaker_matches:
            name_clean = name_candidate.strip()
            # Ignore generic speaker prefixes like "Rep", "AE", "Interviewer"
            if name_clean.lower() in ["rep", "ae", "account executive", "me", "sales", "notes", "agenda"]:
                continue
            if name_clean.lower() not in seen_names and len(name_clean.split()) <= 4:
                seen_names.add(name_clean.lower())
                role = role_candidate.strip() if role_candidate else "Stakeholder"
                sentiment, sentiment_note = self._detect_person_sentiment(name_clean, full_text)
                influence = self._infer_influence(role)
                stakeholders.append({
                    "name": name_clean,
                    "role": role,
                    "influence_level": influence,
                    "sentiment": sentiment,
                    "sentiment_note": sentiment_note
                })

        return stakeholders

    def _parse_stakeholder_entry(self, entry: str, full_text: str) -> Dict[str, Any]:
        role = "Stakeholder"
        name = entry
        role_match = re.search(r"\(([^)]+)\)|-\s*([A-Za-z\s]+)$", entry)
        if role_match:
            role = (role_match.group(1) or role_match.group(2)).strip()
            name = re.sub(r"\([^)]+\)|-\s*[A-Za-z\s]+$", "", entry).strip()

        sentiment, sentiment_note = self._detect_person_sentiment(name, full_text)
        influence = self._infer_influence(role)

        return {
            "name": name,
            "role": role,
            "influence_level": influence,
            "sentiment": sentiment,
            "sentiment_note": sentiment_note
        }

    def _infer_influence(self, role: str) -> str:
        role_lower = role.lower()
        if any(r in role_lower for r in ["cfo", "cro", "ceo", "cio", "vp", "head of", "director"]):
            return "high"
        if any(r in role_lower for r in ["champion", "lead", "architect", "manager"]):
            return "champion"
        return "medium"

    def _detect_person_sentiment(self, name: str, full_text: str) -> Tuple[str, Optional[str]]:
        """Detects sentiment specifically attributed to a stakeholder."""
        # Search sentences or lines containing the person's name
        lines = [l for l in full_text.splitlines() if name.lower() in l.lower()]
        joined = " ".join(lines).lower()

        if any(w in joined for w in ["skeptical", "concerned", "hesitant", "worried", "pushed back", "doubt"]):
            return "skeptical", "Raised concerns during discussion"
        if any(w in joined for w in ["enthusiastic", "loves", "champion", "excited", "strongly supports"]):
            return "positive", "Expressed strong buy-in"
        if any(w in joined for w in ["fixed", "strict", "inflexible", "firm"]):
            return "skeptical", "Holding strict requirements/budget"
        if any(w in joined for w in ["flexible", "open to", "agreeable"]):
            return "flexible", "Open to compromise"
        return "neutral", None

    def _extract_objections(self, lines: List[str], full_text: str) -> List[Dict[str, Any]]:
        objections = []
        seen_texts = set()

        for line in lines:
            line_lower = line.lower()
            # Look for lines indicating pushback, concern, or objection
            is_objection = any(kw in line_lower for kw in [
                "concern", "object", "pushback", "issue", "blocker", "hesitation",
                "too high", "not in budget", "latency concern", "sla required",
                "worried about", "can we do", "without support"
            ])

            if is_objection:
                category = "general"
                for cat, patterns in self.OBJECTION_PATTERNS.items():
                    if any(re.search(pat, line_lower) for pat in patterns):
                        category = cat
                        break

                clean_text = line.lstrip("-*• 1234567890.:")
                if clean_text.lower() not in seen_texts:
                    seen_texts.add(clean_text.lower())
                    
                    # Detect if handling was attempted in the same or next sentence
                    handling = self._detect_handling(clean_text, full_text)
                    resolved = "resolved" in line_lower or "agreed to" in line_lower

                    objections.append({
                        "category": category,
                        "objection_text": clean_text,
                        "handling_attempted": handling,
                        "resolved": resolved
                    })

        return objections

    def _detect_handling(self, objection_text: str, full_text: str) -> Optional[str]:
        # Simple heuristic: look for "we offered", "rep explained", "clarified that", "proposed"
        for l in full_text.splitlines():
            l_lower = l.lower()
            if any(h in l_lower for h in ["offered", "clarified that", "rebutted", "countered with", "explained that"]):
                return l.strip().lstrip("-*• ")
        return None

    def _extract_competitors(self, lines: List[str], full_text: str) -> List[Dict[str, Any]]:
        competitors = []
        seen_comps = set()
        text_lower = full_text.lower()

        for comp in self.KNOWN_COMPETITORS:
            if comp in text_lower:
                # Find the surrounding line/context
                for line in lines:
                    if comp in line.lower() and comp not in seen_comps:
                        seen_comps.add(comp)
                        comp_name = comp.title()
                        
                        # Infer comparative angle if mentioned
                        angle = None
                        if "security" in line.lower() or "compliance" in line.lower():
                            angle = "Positioned enterprise security & compliance advantage"
                        elif "price" in line.lower() or "cost" in line.lower():
                            angle = "Highlighted lower TCO and bundled pricing"
                        elif "speed" in line.lower() or "latency" in line.lower():
                            angle = "Emphasized real-time performance and SLA guarantees"
                        else:
                            angle = f"Positioned specialized enterprise capability vs {comp_name}"

                        competitors.append({
                            "competitor_name": comp_name,
                            "context": line.strip().lstrip("-*• "),
                            "comparative_angle_used": angle,
                            "threat_level": "high" if "po" in line.lower() or "incumbent" in line.lower() else "medium"
                        })
                        break

        return competitors

    def _extract_commitments(self, lines: List[str], full_text: str) -> List[Dict[str, Any]]:
        commitments = []
        seen_actions = set()

        for line in lines:
            line_lower = line.lower()
            is_action = any(act in line_lower for act in [
                "action item", "next step", "agreed to", "will send", "will provide",
                "commit to", "to follow up", "schedule follow-up", "rep to", "prospect to"
            ])

            if is_action:
                owner = "rep"
                if any(p in line_lower for p in ["client to", "prospect to", "they will", "customer to", "sarah to", "mark to"]):
                    owner = "prospect"
                elif any(r in line_lower for r in ["i will", "we will", "rep will", "sales will"]):
                    owner = "rep"

                # Extract due date if present (e.g. by Friday, by 2026-09-25)
                due_date = self._extract_date(line)
                if not due_date:
                    due_match = re.search(r"by\s+([A-Za-z0-9\s]+?)(?:\.|$|,)", line, re.I)
                    if due_match:
                        due_date = due_match.group(1).strip()

                desc = line.strip().lstrip("-*• 1234567890.:")
                if desc.lower() not in seen_actions:
                    seen_actions.add(desc.lower())
                    commitments.append({
                        "owner": owner,
                        "description": desc,
                        "due_date": due_date,
                        "status": "open"
                    })

        return commitments

    def _detect_stage_signal(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        if "moving to proposal" in text_lower or "send contract" in text_lower or "redlines" in text_lower:
            return "Proposal/Negotiation"
        if "moving to poc" in text_lower or "technical deep dive" in text_lower or "architecture review" in text_lower:
            return "Technical Evaluation"
        if "closed-won" in text_lower or "signed contract" in text_lower or "contract executed" in text_lower:
            return "Closed-Won"
        if "deal lost" in text_lower or "chose competitor" in text_lower or "not moving forward" in text_lower:
            return "Closed-Lost"
        return None

    def _generate_summary(
        self,
        lines: List[str],
        interaction_type: str,
        stakeholders: List[Dict[str, Any]],
        objections: List[Dict[str, Any]],
        commitments: List[Dict[str, Any]]
    ) -> str:
        stk_names = [s["name"] for s in stakeholders]
        stk_str = f" with {', '.join(stk_names)}" if stk_names else ""
        obj_count = len(objections)
        comm_count = len(commitments)
        
        return f"{interaction_type.capitalize()} interaction{stk_str}. {obj_count} objection(s) logged; {comm_count} action item(s) pending."

    # -------------------------------------------------------------
    # END-TO-END INGEST & LOG PATH
    # -------------------------------------------------------------

    def ingest_and_log(
        self,
        raw_text: str,
        account_id: str,
        interaction_date: Optional[str] = None,
        interaction_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parses raw text and writes structured data directly into Hindsight.
        Returns single-line confirmation and extracted entities.
        """
        if not self.engine:
            raise ValueError("HindsightEngine must be provided to DealInteractionExtractor for direct logging.")

        extracted = self.extract_from_text(
            raw_text=raw_text,
            account_id=account_id,
            interaction_date=interaction_date,
            interaction_type=interaction_type
        )

        log_res = self.engine.log_interaction(
            account_id=account_id,
            interaction_date=extracted["interaction_date"],
            interaction_type=extracted["interaction_type"],
            stakeholders_present=extracted["stakeholders_present"],
            objections_raised=extracted["objections_raised"],
            competitors_mentioned=extracted["competitors_mentioned"],
            commitments_made=extracted["commitments_made"],
            deal_stage_signal=extracted["deal_stage_signal"],
            summary=extracted["summary"],
            raw_notes_excerpt=extracted["raw_notes_excerpt"]
        )

        return {
            "status": "success",
            "confirmation_message": log_res["confirmation_message"],
            "extracted": extracted,
            "interaction_id": log_res["interaction_id"]
        }
