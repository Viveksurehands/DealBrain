"""
Hindsight Engine
Persistent deal memory store with zero-hallucination read/write contract,
stakeholder tracking, objection playbooks, and cross-deal retrospective analytics.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

DEFAULT_STORE_PATH = Path(__file__).resolve().parent / "hindsight_store.json"

class HindsightEngine:
    def __init__(self, store_path: Optional[str] = None):
        self.store_path = Path(store_path) if store_path else DEFAULT_STORE_PATH
        self._ensure_store_exists()
        self.data: Dict[str, Any] = self._load()

    def _ensure_store_exists(self):
        if not self.store_path.exists():
            initial_data = {
                "accounts": {},
                "patterns": {
                    "pricing_pushback": [],
                    "competitor_mentions": [],
                    "win_loss_trends": []
                },
                "metadata": {
                    "version": "1.0",
                    "last_updated": datetime.now().isoformat(),
                    "total_records": 0
                }
            }
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, indent=2)

    def _load(self) -> Dict[str, Any]:
        with open(self.store_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self):
        self.data["metadata"]["last_updated"] = datetime.now().isoformat()
        total_interactions = sum(
            len(acc.get("interaction_history", [])) for acc in self.data["accounts"].values()
        )
        self.data["metadata"]["total_records"] = total_interactions
        
        # Write to temporary file first for atomic safety
        temp_path = self.store_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        temp_path.replace(self.store_path)

    # -------------------------------------------------------------
    # READ PATH & RESOLUTION CONTRACT
    # -------------------------------------------------------------

    def lookup_account(self, query: str) -> Dict[str, Any]:
        """
        Query Hindsight for an account by ID or name.
        Enforces DealBrain memory contract:
        - If not found: return explicit 'No prior history found...'
        - If ambiguous: return candidate list for confirmation
        - If found: return account record
        """
        clean_query = query.strip()
        if not clean_query:
            return {
                "status": "error",
                "message": "Query string cannot be empty."
            }

        # 1. Exact Account ID match
        if clean_query in self.data["accounts"]:
            return {
                "status": "found",
                "match_type": "exact_id",
                "account": self.data["accounts"][clean_query]
            }

        # 2. Match by company name (exact case-insensitive or partial)
        exact_name_matches = []
        partial_name_matches = []
        q_lower = clean_query.lower()

        for acc_id, acc in self.data["accounts"].items():
            name = acc.get("company_name", "").strip()
            name_lower = name.lower()
            if name_lower == q_lower:
                exact_name_matches.append(acc)
            elif q_lower in name_lower or name_lower in q_lower:
                partial_name_matches.append(acc)

        if len(exact_name_matches) == 1:
            return {
                "status": "found",
                "match_type": "exact_name",
                "account": exact_name_matches[0]
            }

        candidates = exact_name_matches if exact_name_matches else partial_name_matches

        if len(candidates) > 1:
            return {
                "status": "ambiguous",
                "message": f"Multiple records found matching '{query}'. Confirm which record before proceeding.",
                "candidates": [
                    {
                        "account_id": c["account_id"],
                        "company_name": c["company_name"],
                        "current_stage": c.get("current_stage"),
                        "last_activity_date": c.get("last_activity_date")
                    }
                    for c in candidates
                ]
            }

        if len(candidates) == 1:
            return {
                "status": "found",
                "match_type": "partial_name",
                "account": candidates[0]
            }

        return {
            "status": "not_found",
            "message": "No prior history found for this account in Hindsight"
        }

    def get_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        return self.data["accounts"].get(account_id)

    def list_accounts(self) -> List[Dict[str, Any]]:
        return list(self.data["accounts"].values())

    def get_unresolved_objections(self, account_id: str) -> List[Dict[str, Any]]:
        acc = self.get_account(account_id)
        if not acc:
            return []
        return [obj for obj in acc.get("objections", []) if not obj.get("resolved", False)]

    def get_open_commitments(self, account_id: str) -> List[Dict[str, Any]]:
        acc = self.get_account(account_id)
        if not acc:
            return []
        return [c for c in acc.get("commitments", []) if c.get("status") == "open"]

    def get_competitors_in_play(self, account_id: str) -> List[Dict[str, Any]]:
        acc = self.get_account(account_id)
        if not acc:
            return []
        # Return unique competitors with latest mention context
        competitor_map = {}
        for comp in acc.get("competitors", []):
            name = comp["competitor_name"]
            competitor_map[name] = comp
        return list(competitor_map.values())

    def get_stakeholders_sentiment_delta(self, account_id: str) -> List[Dict[str, Any]]:
        """
        Analyzes stakeholder sentiment shifts over time.
        Identifies notable changes since the previous touchpoints.
        """
        acc = self.get_account(account_id)
        if not acc:
            return []

        stakeholders_report = []
        for contact_id, s in acc.get("stakeholders", {}).items():
            history = s.get("sentiment_history", [])
            shift_note = None
            if len(history) >= 2:
                prev = history[-2]
                curr = history[-1]
                if prev["sentiment"] != curr["sentiment"]:
                    shift_note = f"Shifted from '{prev['sentiment']}' on {prev['date']} to '{curr['sentiment']}' on {curr['date']}"
                    if curr.get("notes"):
                        shift_note += f" ({curr['notes']})"
            
            stakeholders_report.append({
                "contact_id": contact_id,
                "name": s["name"],
                "role": s["role"],
                "influence_level": s.get("influence_level", "medium"),
                "current_sentiment": s.get("current_sentiment", "neutral"),
                "notable_change": shift_note
            })
        return stakeholders_report

    # -------------------------------------------------------------
    # WRITE PATH & INTERACTION LOGGING
    # -------------------------------------------------------------

    def upsert_account(self, account_id: str, company_name: str, **kwargs) -> Dict[str, Any]:
        """Creates or updates core account details."""
        if account_id not in self.data["accounts"]:
            self.data["accounts"][account_id] = {
                "account_id": account_id,
                "company_name": company_name,
                "industry": kwargs.get("industry"),
                "arr_estimate": kwargs.get("arr_estimate"),
                "current_stage": kwargs.get("current_stage", "Discovery"),
                "status": kwargs.get("status", "active"),
                "last_activity_date": kwargs.get("last_activity_date", datetime.now().strftime("%Y-%m-%d")),
                "champion_id": kwargs.get("champion_id"),
                "economic_buyer_id": kwargs.get("economic_buyer_id"),
                "created_at": datetime.now().isoformat(),
                "stakeholders": {},
                "objections": [],
                "competitors": [],
                "commitments": [],
                "interaction_history": []
            }
        else:
            acc = self.data["accounts"][account_id]
            acc["company_name"] = company_name
            for k in ["industry", "arr_estimate", "current_stage", "status", "champion_id", "economic_buyer_id"]:
                if k in kwargs and kwargs[k] is not None:
                    acc[k] = kwargs[k]
        self._save()
        return self.data["accounts"][account_id]

    def log_interaction(
        self,
        account_id: str,
        interaction_date: str,
        interaction_type: str,
        stakeholders_present: Optional[List[Dict[str, Any]]] = None,
        objections_raised: Optional[List[Dict[str, Any]]] = None,
        competitors_mentioned: Optional[List[Dict[str, Any]]] = None,
        commitments_made: Optional[List[Dict[str, Any]]] = None,
        deal_stage_signal: Optional[str] = None,
        summary: str = "",
        raw_notes_excerpt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Strict Write Path:
        1. Ingests structured facts without speculative extrapolation.
        2. Updates stakeholder profiles and sentiment timeline.
        3. Appends objections, competitor mentions, and commitments with interaction provenance.
        4. Updates account last_activity_date and current_stage if signaled.
        5. Returns single-line confirmation string.
        """
        acc = self.get_account(account_id)
        if not acc:
            raise ValueError(f"Account '{account_id}' does not exist in Hindsight. Upsert account first.")

        interaction_id = f"int_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        
        # 1. Update/Add Stakeholders
        recorded_stakeholder_names = []
        if stakeholders_present:
            for s in stakeholders_present:
                name = s.get("name")
                if not name:
                    continue
                recorded_stakeholder_names.append(name)
                contact_id = s.get("contact_id") or f"c_{name.lower().replace(' ', '_')}"
                sentiment = s.get("sentiment", "neutral")
                sentiment_note = s.get("sentiment_note")
                role = s.get("role", "Stakeholder")
                influence = s.get("influence_level", "medium")

                if contact_id not in acc["stakeholders"]:
                    acc["stakeholders"][contact_id] = {
                        "contact_id": contact_id,
                        "name": name,
                        "role": role,
                        "influence_level": influence,
                        "current_sentiment": sentiment,
                        "sentiment_history": [
                            {"date": interaction_date, "sentiment": sentiment, "notes": sentiment_note}
                        ]
                    }
                else:
                    curr_stk = acc["stakeholders"][contact_id]
                    curr_stk["name"] = name
                    if role != "Stakeholder":
                        curr_stk["role"] = role
                    if influence != "medium":
                        curr_stk["influence_level"] = influence
                    # Only append sentiment point if sentiment changed or there is a specific note
                    if curr_stk.get("current_sentiment") != sentiment or sentiment_note:
                        curr_stk["sentiment_history"].append({
                            "date": interaction_date,
                            "sentiment": sentiment,
                            "notes": sentiment_note
                        })
                        curr_stk["current_sentiment"] = sentiment

        # 2. Objections
        new_objection_ids = []
        if objections_raised:
            for obj in objections_raised:
                obj_id = f"obj_{uuid.uuid4().hex[:8]}"
                record = {
                    "objection_id": obj_id,
                    "interaction_id": interaction_id,
                    "date_raised": interaction_date,
                    "category": obj.get("category", "general"),  # pricing, technical, competitive, timing
                    "objection_text": obj.get("objection_text") or obj.get("objection", ""),
                    "handling_attempted": obj.get("handling_attempted"),
                    "resolved": obj.get("resolved", False)
                }
                acc["objections"].append(record)
                new_objection_ids.append(obj_id)

        # 3. Competitors
        new_competitor_ids = []
        if competitors_mentioned:
            for comp in competitors_mentioned:
                comp_id = f"comp_{uuid.uuid4().hex[:8]}"
                record = {
                    "mention_id": comp_id,
                    "interaction_id": interaction_id,
                    "date_mentioned": interaction_date,
                    "competitor_name": comp.get("name") or comp.get("competitor_name", ""),
                    "context": comp.get("context", ""),
                    "comparative_angle_used": comp.get("comparative_angle_used"),
                    "threat_level": comp.get("threat_level", "medium")
                }
                acc["competitors"].append(record)
                new_competitor_ids.append(comp_id)

        # 4. Commitments
        new_commitment_ids = []
        if commitments_made:
            for comm in commitments_made:
                comm_id = f"comm_{uuid.uuid4().hex[:8]}"
                record = {
                    "commitment_id": comm_id,
                    "interaction_id": interaction_id,
                    "date_created": interaction_date,
                    "owner": comm.get("owner", "unassigned"),
                    "description": comm.get("description", ""),
                    "due_date": comm.get("due_date"),
                    "status": comm.get("status", "open")
                }
                acc["commitments"].append(record)
                new_commitment_ids.append(comm_id)

        # 5. Deal Stage Signal & Last Activity
        stage_changed = False
        if deal_stage_signal and deal_stage_signal != acc.get("current_stage"):
            acc["current_stage"] = deal_stage_signal
            stage_changed = True
        acc["last_activity_date"] = interaction_date

        # 6. Interaction Record
        interaction_record = {
            "interaction_id": interaction_id,
            "account_id": account_id,
            "interaction_date": interaction_date,
            "interaction_type": interaction_type,
            "summary": summary,
            "stakeholders_present": recorded_stakeholder_names,
            "objection_ids": new_objection_ids,
            "competitor_mention_ids": new_competitor_ids,
            "commitment_ids": new_commitment_ids,
            "deal_stage_signal": deal_stage_signal if stage_changed else None,
            "raw_notes_excerpt": raw_notes_excerpt
        }
        acc["interaction_history"].append(interaction_record)

        self._save()

        # Produce strict single-line confirmation
        confirmation_parts = []
        if new_objection_ids:
            confirmation_parts.append(f"{len(new_objection_ids)} new objection{'s' if len(new_objection_ids) > 1 else ''}")
        if new_competitor_ids:
            confirmation_parts.append(f"{len(new_competitor_ids)} competitor mention{'s' if len(new_competitor_ids) > 1 else ''}")
        if new_commitment_ids:
            confirmation_parts.append(f"{len(new_commitment_ids)} open action item{'s' if len(new_commitment_ids) > 1 else ''}")
        if stage_changed:
            confirmation_parts.append(f"stage changed to '{deal_stage_signal}'")

        summary_line = ", ".join(confirmation_parts) if confirmation_parts else "interaction logged"
        confirmation_msg = f"Logged: {summary_line}."

        return {
            "status": "success",
            "interaction_id": interaction_id,
            "confirmation_message": confirmation_msg,
            "counts": {
                "objections": len(new_objection_ids),
                "competitors": len(new_competitor_ids),
                "commitments": len(new_commitment_ids)
            }
        }

    # -------------------------------------------------------------
    # PATTERNS & RETROSPECTIVES (WIN/LOSS CORRELATION)
    # -------------------------------------------------------------

    def query_cross_deal_patterns(
        self,
        category: Optional[str] = None,
        competitor_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cross-reference objections/competitors across all deals in Hindsight.
        Calculates win-rates and effective counter-tactics with clear sample sizes.
        """
        total_deals_analyzed = len(self.data["accounts"])
        matching_deals = []
        won_count = 0
        lost_count = 0
        successful_tactics = []

        for acc in self.data["accounts"].values():
            status = acc.get("status", "active")
            is_match = False
            
            if category:
                for obj in acc.get("objections", []):
                    if obj.get("category", "").lower() == category.lower():
                        is_match = True
                        if status == "won" and obj.get("handling_attempted"):
                            successful_tactics.append(obj.get("handling_attempted"))
            
            if competitor_name:
                for comp in acc.get("competitors", []):
                    if competitor_name.lower() in comp.get("competitor_name", "").lower():
                        is_match = True
                        if status == "won" and comp.get("comparative_angle_used"):
                            successful_tactics.append(comp.get("comparative_angle_used"))

            if is_match:
                matching_deals.append(acc)
                if status == "won":
                    won_count += 1
                elif status == "lost":
                    lost_count += 1

        sample_size = len(matching_deals)
        win_rate = (won_count / (won_count + lost_count) * 100) if (won_count + lost_count) > 0 else None

        return {
            "query": {"category": category, "competitor": competitor_name},
            "sample_size": sample_size,
            "won_count": won_count,
            "lost_count": lost_count,
            "win_rate_percentage": round(win_rate, 1) if win_rate is not None else "N/A (active/insufficient closed data)",
            "effective_tactics": list(set(successful_tactics)),
            "pattern_statement": f"Pattern across {sample_size} deals suggests: " + (
                f"Win rate is {round(win_rate, 1)}% when addressed early with proven tactics." 
                if win_rate is not None else "Data currently forming across active deals."
            )
        }
