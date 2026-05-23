"""Musawo AI — Agentic iCCM Triage Workflow.

Multi-step health assessment agent that guides VHTs through the
official iCCM protocol: Assess → Classify → Treat/Refer.

Unlike single-shot RAG, this agent:
1. Asks follow-up questions to gather complete clinical picture
2. Runs danger-sign detection at EVERY step
3. Classifies condition using iCCM decision tree
4. Generates treatment protocol OR referral with pre-referral treatment
5. Schedules follow-up reminder

Adapted from URA Chatbot Phase 14 supervisor pattern.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.models import (
    EscalationAction,
    Mode,
    RedFlag,
    Severity,
    TriageResult,
)
from app.i18n import t

logger = logging.getLogger("musawo.triage_agent")


class TriagePhase(str, Enum):
    INITIAL = "initial"           # First contact — what's the main complaint?
    DANGER_CHECK = "danger_check" # Check for general danger signs
    ASSESS = "assess"             # Gather specific symptoms
    CLASSIFY = "classify"         # Determine severity classification
    TREAT_REFER = "treat_refer"  # Generate treatment or referral
    FOLLOW_UP = "follow_up"      # Schedule follow-up


@dataclass
class TriageState:
    """Stateful triage session for a single patient encounter."""
    phase: TriagePhase = TriagePhase.INITIAL
    patient_age_months: int | None = None
    main_complaint: str = ""
    symptoms_reported: list[str] = field(default_factory=list)
    danger_signs_found: list[str] = field(default_factory=list)
    vital_signs: dict[str, Any] = field(default_factory=dict)
    classifications: list[str] = field(default_factory=list)
    treatment_given: list[str] = field(default_factory=list)
    referred: bool = False
    follow_up_hours: int = 0
    questions_asked: int = 0
    max_questions: int = 5  # Don't ask more than 5 follow-ups
    locale: str = "en"  # User's language
    # Clinical extensions
    dehydration_level: str = "unknown"  # none / some / severe / unknown
    muac_mm: int | None = None  # Mid-upper arm circumference in mm
    nutrition_status: str = "unknown"  # normal / MAM / SAM / unknown


# ── Danger sign patterns (hard-coded, no LLM needed) ──────────────────

GENERAL_DANGER_SIGNS = {
    # English + Luganda + Runyankole + Swahili patterns
    "unable to drink or breastfeed": (
        r"(not|unable|can.?t)\s*(drink|breastfeed|eat|feed|suckle)"
        r"|tayinza\s*ku(nywa|lya|yonsa)"        # Luganda
        r"|tarikubashor[ai]\s*ku(rya|nywera|gonza)"  # Runyankole
        r"|hawezi\s*ku(nywa|la|nyonyesha)"       # Swahili
    ),
    "vomiting everything": (
        r"vomit(s|ing)?\s*(everything|all)"
        r"|asesema\s*byo?nna|okusesema\s*byonna"  # Luganda
        r"|ashuuha\s*byo?na|okushuuha\s*byoona"   # Runyankole
        r"|kutapika\s*kila\s*kitu"                  # Swahili
    ),
    "convulsions": (
        r"convuls|fits|seizure|jerking"
        r"|okusaamusaamu|okutuuka"    # Luganda
        r"|okushandaga"                # Runyankole
        r"|degedege|kifafa"            # Swahili
    ),
    "lethargic or unconscious": (
        r"(lethargic|unconscious|drowsy|very\s*sleepy|not\s*responsive|cannot\s*wake)"
        r"|okuzimbulukuka|tazuukuka"   # Luganda
        r"|okuzirikira|tarikuzuukuka"  # Runyankole
        r"|kupoteza\s*fahamu"          # Swahili
    ),
    "chest indrawing": (
        r"chest\s*(indraw|in-draw|retract)"
        r"|ekifuba\s*kyeyongera"       # Luganda
        r"|kifua\s*kinaingia"          # Swahili
    ),
    "severe bleeding": (
        r"(severe|heavy|lot\s*of)\s*bleed"
        r"|omusaayi\s*mungi|okubaaga\s*nnyo"  # Luganda
        r"|okuteera\s*ennyo"                    # Runyankole
        r"|kutoka\s*damu\s*nyingi"              # Swahili
    ),
    "high fever in infant": (
        r"(high|very)\s*fever.*(baby|infant|newborn|child)"
        r"|omusujja\s*mu(ngi|nene).*omwana"  # Luganda
        r"|homa\s*kali.*mtoto"                # Swahili
    ),
    "stiff neck": (
        r"stiff\s*neck"
        r"|ensingo\s*enkakanyavu"   # Luganda
        r"|shingo\s*ngumu"          # Swahili
    ),
    "bulging fontanelle": r"bulg(ing|ed)\s*fontanel",
    "severe malnutrition": (
        r"(severe|very)\s*(maln|wast|thin|swollen\s*feet)"
        r"|utapiamlo\s*mkubwa"     # Swahili
    ),
}

# ── Symptom classification rules (iCCM decision tree) ─────────────────

MALARIA_INDICATORS = {
    "fever", "hot body", "chills", "rigors", "sweating",
    "headache", "body pain", "joint pain", "vomiting",
    # Luganda
    "omusujja", "musujja", "omutwe", "okusesema", "okunyiinya",
    # Runyankole
    "omushuija", "okushuuha",
    # Swahili
    "homa", "kutapika", "kichwa", "kutetemeka",
}

PNEUMONIA_INDICATORS = {
    "cough", "difficult breathing", "fast breathing", "noisy breathing",
    "chest pain", "wheeze", "stridor",
    # Luganda
    "okufuuwa", "okukola", "okufuba", "okussa", "ekifuba",
    # Runyankole
    "okukora", "okuhuuha",
    # Swahili
    "kikohozi", "kupumua", "kifua",
}

DIARRHOEA_INDICATORS = {
    "diarrhoea", "diarrhea", "loose stool", "watery stool", "blood in stool",
    "vomiting", "dehydration", "sunken eyes",
    # Luganda
    "ekiddukaano", "okugenda", "amazzi", "amaaso",
    # Runyankole
    "okushaarira",
    # Swahili
    "kuharisha", "kutapika", "maji",
}

MEASLES_INDICATORS = {
    "measles", "rash", "red eyes", "runny nose", "koplik",
    "kawumpuli", "akaloosa",  # Luganda
    "kahumpuli",  # Runyankole
    "surua", "upele",  # Swahili
}

MALNUTRITION_INDICATORS = {
    "malnutrition", "wasting", "thin", "swollen feet", "oedema",
    "muac", "not gaining weight", "kwashiorkor", "marasmus",
    "stunting", "underweight", "not growing",
    # Swahili
    "utapiamlo", "kukonda",
}

# ── Dehydration assessment rules (iCCM: Plan A/B/C) ─────────────────

SEVERE_DEHYDRATION_SIGNS = {
    "lethargic", "unconscious", "sunken eyes", "not able to drink",
    "skin pinch very slow", "very slow", "cannot drink",
}
SOME_DEHYDRATION_SIGNS = {
    "restless", "irritable", "thirsty", "drinks eagerly",
    "skin pinch slow", "sunken", "dry mouth",
}

# ── MUAC thresholds (mm) for children 6-59 months ────────────────────
MUAC_SAM = 115   # < 115mm = Severe Acute Malnutrition → REFER
MUAC_MAM = 125   # 115-124mm = Moderate Acute Malnutrition → supplementary feeding

# ── Breathing rate thresholds (iCCM protocol) ─────────────────────────

FAST_BREATHING_THRESHOLD = {
    # age_months: breaths_per_minute
    (2, 11): 50,    # 2-11 months: ≥50
    (12, 59): 40,   # 12-59 months: ≥40
}


class TriageAgent:
    """Stateful agent that guides VHTs through iCCM assessment."""

    def __init__(self, retriever=None):
        from threading import Lock
        self._sessions: dict[str, TriageState] = {}
        self._lock = Lock()
        self._retriever = retriever  # Optional: HybridRetriever for evidence-backed responses

    def get_or_create_state(self, session_id: str) -> TriageState:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = TriageState()
            return self._sessions[session_id]

    def process(self, session_id: str, user_input: str, locale: str = "en") -> dict[str, Any]:
        """Process user input and return agent response with next action.

        Returns dict with:
        - response: str (agent's response text)
        - phase: str (current triage phase)
        - triage: TriageResult | None
        - follow_up_question: str | None
        - assessment_complete: bool
        """
        state = self.get_or_create_state(session_id)
        state.locale = locale
        user_lower = user_input.lower().strip()

        # ── Always check for danger signs at every step ───────────
        newly_found = self._check_danger_signs(user_lower, state)

        # If danger signs found at ANY point → immediate referral
        if state.danger_signs_found and state.phase not in (
            TriagePhase.TREAT_REFER, TriagePhase.FOLLOW_UP
        ):
            state.phase = TriagePhase.TREAT_REFER
            state.referred = True
            return self._generate_emergency_referral(state, newly_found)

        # ── Phase-based processing ────────────────────────────────
        if state.phase == TriagePhase.INITIAL:
            return self._handle_initial(state, user_lower)

        elif state.phase == TriagePhase.DANGER_CHECK:
            return self._handle_danger_check(state, user_lower)

        elif state.phase == TriagePhase.ASSESS:
            return self._handle_assess(state, user_lower)

        elif state.phase == TriagePhase.CLASSIFY:
            return self._handle_classify(state)

        elif state.phase == TriagePhase.TREAT_REFER:
            return self._handle_treat_refer(state)

        elif state.phase == TriagePhase.FOLLOW_UP:
            return self._handle_follow_up(state, user_lower)

        return self._respond(state, "How can I help with this patient?")

    # Negation patterns: "no convulsions", "not vomiting", "hakuna", "tewali", etc.
    _NEGATION_RE = re.compile(
        r"\b(no|not|never|without|hasn.?t|hasn.?t had|don.?t have|does not|didn.?t"
        r"|tewali|talina|si|hakuna|hana|bwatali|tatina)\b",
        re.I,
    )

    def _check_danger_signs(self, text: str, state: TriageState) -> list[str]:
        """Check for danger signs in user input. Returns newly found signs.

        Skips matches that are immediately preceded by a negation word
        (e.g. "no convulsions", "not vomiting", "hakuna degedege").
        """
        newly_found = []
        for sign_name, pattern in GENERAL_DANGER_SIGNS.items():
            match = re.search(pattern, text, re.I)
            if not match or sign_name in state.danger_signs_found:
                continue
            # Check for negation within 4 words before the match
            prefix = text[:match.start()].strip()
            last_words = prefix.split()[-4:] if prefix else []
            prefix_text = " ".join(last_words)
            if self._NEGATION_RE.search(prefix_text):
                continue  # Negated — skip this match
            state.danger_signs_found.append(sign_name)
            newly_found.append(sign_name)
        return newly_found

    # Patterns that indicate an informational/protocol question (not a patient case)
    _INFO_QUERY_RE = re.compile(
        r"(what is|what are|how (to|do|much|many|should)|dosage|dose|"
        r"when (to|should)|explain|tell me about|difference between|"
        r"how (is|can) .* (prepared|given|used|administered)|"
        r"protocol for|steps to|side effect|schedule|"
        # Luganda
        r"kiki|ki ekikolwa|ntya|bwe bagiwa|"
        # Swahili
        r"nini|vipi|kiasi gani|jinsi ya)",
        re.I,
    )

    def _handle_info_query(self, state: TriageState, text: str) -> dict | None:
        """Detect and answer informational/protocol questions directly.

        Returns a direct answer using the retriever if the query is factual
        (e.g. dosage, protocol, preparation steps). Returns None if it's
        a patient case that needs the triage flow.
        """
        if not self._INFO_QUERY_RE.search(text):
            return None
        if not self._retriever:
            return None

        loc = state.locale
        try:
            # Extract clinical terms from the question for focused retrieval
            from app.service import _enrich_query_for_retrieval
            # Build a focused search: strip question words, keep clinical terms
            clinical_terms = re.findall(
                r"\b(ors|zinc|malaria|pneumonia|diarrhoea|diarrhea|fever|cough|rdt|"
                r"amoxicillin|act|paracetamol|vitamin|dehydration|breastfeed|immuniz|"
                r"vaccin|dosage|dose|treatment|muac|breathing|convuls|measles|"
                r"omusujja|ekiddukaano|okufuuwa|homa|kuharisha|kikohozi)\b",
                text, re.I,
            )
            search_q = " ".join(clinical_terms) if clinical_terms else text
            search_q = _enrich_query_for_retrieval(search_q, loc)
            hits = self._retriever.search(query=search_q, top_k=3, mode_filter=None)
            if not hits or max(h.score for h in hits) < 0.1:
                return None

            # Build a direct answer from passages
            response_parts = []
            for i, hit in enumerate(hits[:3]):
                source = hit.metadata.get("source", "MoH")
                section = hit.metadata.get("section", "")
                label = f"[{i+1}] {source}"
                if section:
                    label += f" — {section}"

                # Format the passage text as bullets
                sentences = re.split(r'(?<=[.!:])\s+(?=[A-Z(])', hit.text)
                bullets = []
                for sent in sentences[:6]:
                    sent = sent.strip()
                    if not sent:
                        continue
                    for term in ["REFER", "IMMEDIATELY", "DANGER", "DO NOT", "MUST"]:
                        sent = sent.replace(term, f"**{term}**")
                    bullets.append(f"- {sent}")
                if bullets:
                    response_parts.append(f"**{label}**\n\n" + "\n".join(bullets))

            if not response_parts:
                return None

            answer = "## " + t("triage_manage_home", loc).split(".")[0] + "\n\n"
            answer += "\n\n".join(response_parts)
            answer += "\n\n---\n*" + t("disclaimer", loc) + "*"

            # Mark this as a completed informational query (no triage needed)
            state.phase = TriagePhase.FOLLOW_UP
            return {
                "response": answer,
                "phase": state.phase.value,
                "triage": None,
                "follow_up_question": None,
                "assessment_complete": True,
            }
        except Exception as e:
            logger.warning("Info query retrieval failed: %s", e)
            return None

    def _handle_initial(self, state: TriageState, text: str) -> dict:
        """Phase 1: Get main complaint and patient age.

        If the query is an informational question (dosage, protocol, how-to),
        answer it directly from the knowledge base instead of starting triage.
        """
        # Check if this is an informational question first
        info_response = self._handle_info_query(state, text)
        if info_response:
            return info_response

        state.main_complaint = text
        state.symptoms_reported.append(text)

        # Try to extract age
        age_match = re.search(r"(\d+)\s*(month|year|week|day)", text, re.I)
        if age_match:
            num = int(age_match.group(1))
            unit = age_match.group(2).lower()
            if "year" in unit:
                state.patient_age_months = num * 12
            elif "month" in unit:
                state.patient_age_months = num
            elif "week" in unit:
                state.patient_age_months = max(1, num // 4)
            elif "day" in unit:
                state.patient_age_months = 0

        # Fast-track: if query already has age + enough symptoms to classify,
        # skip danger check and go straight to classification.
        # This handles queries like "2 year old with fever and rash" in one turn.
        if state.patient_age_months is not None and self._has_enough_info(state):
            # Also extract any vital signs or MUAC from the initial query
            rr_match = re.search(r"(\d+)\s*(?:breath|per minute|/min)", text, re.I)
            if rr_match:
                state.vital_signs["respiratory_rate"] = int(rr_match.group(1))
            rdt_match = re.search(r"rdt\s*(positive|negative|\+|-)", text, re.I)
            if rdt_match:
                state.vital_signs["rdt_result"] = "positive" if rdt_match.group(1) in ("positive", "+") else "negative"
            muac_match = re.search(r"muac\s*(?:is\s*)?(\d+)\s*(mm|cm)?", text, re.I)
            if muac_match:
                val = int(muac_match.group(1))
                unit_m = (muac_match.group(2) or "mm").lower()
                state.muac_mm = val * 10 if unit_m == "cm" else val
                state.nutrition_status = "SAM" if state.muac_mm < MUAC_SAM else ("MAM" if state.muac_mm < MUAC_MAM else "normal")

            state.phase = TriagePhase.CLASSIFY
            return self._handle_classify(state)

        state.phase = TriagePhase.DANGER_CHECK
        loc = state.locale

        questions = []
        if state.patient_age_months is None:
            questions.append(t("triage_ask_age", loc))

        questions.append(t("triage_check_danger", loc))

        return self._respond(
            state,
            f"**{state.main_complaint}**\n\n"
            + "\n".join(questions),
            follow_up=True,
        )

    def _handle_danger_check(self, state: TriageState, text: str) -> dict:
        """Phase 2: Systematic danger sign check."""
        # Extract age if provided
        if state.patient_age_months is None:
            age_match = re.search(r"(\d+)\s*(month|year|week)", text, re.I)
            if age_match:
                num = int(age_match.group(1))
                unit = age_match.group(2).lower()
                state.patient_age_months = num * 12 if "year" in unit else num

        state.symptoms_reported.append(text)

        # Check for positive danger signs in response
        if any(w in text for w in ["yes", "yee", "has", "cannot", "unable", "no"]):
            # Try to identify which specific danger sign
            pass  # Already handled by _check_danger_signs

        state.questions_asked += 1

        # If no danger signs found after check, move to assessment
        if not state.danger_signs_found:
            state.phase = TriagePhase.ASSESS
            return self._generate_assessment_question(state)

        # If danger signs found, _check_danger_signs already set phase
        return self._generate_emergency_referral(state, state.danger_signs_found)

    def _handle_assess(self, state: TriageState, text: str) -> dict:
        """Phase 3: Gather specific symptoms for classification."""
        state.symptoms_reported.append(text)
        state.questions_asked += 1

        # Extract vital signs if mentioned
        rr_match = re.search(r"(\d+)\s*breath", text, re.I)
        if rr_match:
            state.vital_signs["respiratory_rate"] = int(rr_match.group(1))

        temp_match = re.search(r"(\d+\.?\d*)\s*°?[cC]", text)
        if temp_match:
            state.vital_signs["temperature"] = float(temp_match.group(1))

        rdt_match = re.search(r"rdt\s*(positive|negative|\+|-)", text, re.I)
        if rdt_match:
            state.vital_signs["rdt_result"] = "positive" if rdt_match.group(1) in ("positive", "+") else "negative"

        # Extract MUAC if mentioned (e.g., "MUAC 110mm", "MUAC is 12cm")
        muac_match = re.search(r"muac\s*(?:is\s*)?(\d+)\s*(mm|cm)?", text, re.I)
        if muac_match:
            val = int(muac_match.group(1))
            unit = (muac_match.group(2) or "mm").lower()
            state.muac_mm = val * 10 if unit == "cm" else val
            if state.muac_mm < MUAC_SAM:
                state.nutrition_status = "SAM"
            elif state.muac_mm < MUAC_MAM:
                state.nutrition_status = "MAM"
            else:
                state.nutrition_status = "normal"

        # Assess dehydration level from text
        all_text_lower = " ".join(state.symptoms_reported).lower()
        severe_hits = len(SEVERE_DEHYDRATION_SIGNS & set(re.findall(r"\w+", all_text_lower)))
        some_hits = len(SOME_DEHYDRATION_SIGNS & set(re.findall(r"\w+", all_text_lower)))
        if severe_hits >= 2:
            state.dehydration_level = "severe"
        elif some_hits >= 2:
            state.dehydration_level = "some"
        elif "no dehydration" in all_text_lower or "well hydrated" in all_text_lower:
            state.dehydration_level = "none"

        # If we have enough info or hit max questions → classify
        if state.questions_asked >= state.max_questions or self._has_enough_info(state):
            state.phase = TriagePhase.CLASSIFY
            return self._handle_classify(state)

        return self._generate_assessment_question(state)

    def _has_enough_info(self, state: TriageState) -> bool:
        """Check if we have enough symptoms to classify."""
        all_text = " ".join(state.symptoms_reported).lower()
        tokens = set(re.findall(r"\w+", all_text))
        scores = [
            len(MALARIA_INDICATORS & tokens),
            len(PNEUMONIA_INDICATORS & tokens),
            len(DIARRHOEA_INDICATORS & tokens),
            len(MEASLES_INDICATORS & tokens),
            len(MALNUTRITION_INDICATORS & tokens),
        ]
        return max(scores) >= 2 or state.muac_mm is not None

    def _handle_classify(self, state: TriageState) -> dict:
        """Phase 4: Classify based on gathered symptoms (iCCM protocol)."""
        all_text = " ".join(state.symptoms_reported).lower()
        tokens = set(re.findall(r"\w+", all_text))

        # Score each condition
        malaria_score = len(MALARIA_INDICATORS & tokens)
        pneumonia_score = len(PNEUMONIA_INDICATORS & tokens)
        diarrhoea_score = len(DIARRHOEA_INDICATORS & tokens)
        measles_score = len(MEASLES_INDICATORS & tokens)
        malnutrition_score = len(MALNUTRITION_INDICATORS & tokens)

        classifications = []
        if malaria_score >= 2:
            classifications.append("possible_malaria")
        if pneumonia_score >= 2:
            classifications.append("possible_pneumonia")
        if diarrhoea_score >= 2:
            classifications.append("diarrhoea")
        if measles_score >= 2:
            classifications.append("possible_measles")
        if malnutrition_score >= 2 or state.nutrition_status == "SAM":
            classifications.append("severe_malnutrition")
        elif state.nutrition_status == "MAM":
            classifications.append("moderate_malnutrition")

        if not classifications:
            classifications.append("unclassified")

        state.classifications = classifications
        state.phase = TriagePhase.TREAT_REFER
        return self._handle_treat_refer(state)

    def _handle_treat_refer(self, state: TriageState) -> dict:
        """Phase 5: Generate treatment protocol or referral."""
        treatments = []
        severity = Severity.GREEN
        red_flags = []

        if state.danger_signs_found:
            severity = Severity.RED
            state.referred = True
            red_flags = [
                RedFlag(
                    symptom=sign,
                    severity=Severity.RED,
                    action=EscalationAction.EMERGENCY_REFER,
                    detail=f"Danger sign: {sign}. Give pre-referral treatment and REFER IMMEDIATELY.",
                )
                for sign in state.danger_signs_found
            ]
            treatments.append("Give pre-referral treatment and REFER IMMEDIATELY to nearest health facility.")

        for classification in state.classifications:
            if classification == "possible_malaria":
                if state.vital_signs.get("rdt_result") == "positive":
                    age = state.patient_age_months or 24
                    if age < 12:
                        treatments.append("MALARIA (RDT+): Give ACT (Artemether-Lumefantrine) — 1 tablet twice daily for 3 days.")
                    else:
                        treatments.append("MALARIA (RDT+): Give ACT (Artemether-Lumefantrine) — 2 tablets twice daily for 3 days.")
                    state.follow_up_hours = 72
                else:
                    treatments.append("POSSIBLE MALARIA: Perform RDT before treating. If RDT positive → give ACT. If negative → do NOT give ACT, look for other cause of fever.")
                if not severity == Severity.RED:
                    severity = Severity.YELLOW

            elif classification == "possible_pneumonia":
                rr = state.vital_signs.get("respiratory_rate")
                age = state.patient_age_months or 24
                if rr:
                    threshold = 50 if age < 12 else 40
                    if rr >= threshold:
                        treatments.append(
                            f"PNEUMONIA (fast breathing ≥{threshold}/min): "
                            f"Give Amoxicillin {'250' if age < 12 else '500'} mg twice daily for 5 days."
                        )
                        severity = Severity.YELLOW
                        state.follow_up_hours = 48
                    else:
                        treatments.append("Breathing rate is normal. Likely not pneumonia. Monitor and return if worsens.")
                else:
                    treatments.append("COUNT THE BREATHING for 1 FULL MINUTE. Fast breathing = 50/min (2-11 months) or 40/min (12-59 months). If fast → give Amoxicillin.")

            elif classification == "diarrhoea":
                treatments.append("DIARRHOEA: Give ORS — mix 1 packet in 1 litre clean water. Give frequent small sips.")
                age = state.patient_age_months or 24
                zinc_dose = "10 mg" if age < 6 else "20 mg"
                treatments.append(f"Give Zinc {zinc_dose} once daily for 10 days.")
                treatments.append("Continue breastfeeding and feeding.")
                if "blood" in " ".join(state.symptoms_reported).lower():
                    treatments.append("BLOOD IN STOOL → REFER to health facility.")
                    severity = Severity.RED
                    state.referred = True
                # Dehydration severity grading (iCCM Plan A/B/C)
                if state.dehydration_level == "severe":
                    treatments.append("SEVERE DEHYDRATION (Plan C): REFER IMMEDIATELY. Give ORS on the way.")
                    severity = Severity.RED
                    state.referred = True
                elif state.dehydration_level == "some":
                    treatments.append("SOME DEHYDRATION (Plan B): Give ORS — 75ml/kg over 4 hours. Reassess after 4 hours.")
                    severity = max(severity, Severity.YELLOW, key=lambda s: ["GREEN","YELLOW","RED"].index(s.value))
                else:
                    treatments.append("NO/MILD DEHYDRATION (Plan A): Give ORS after each loose stool. Continue feeding.")
                if not severity == Severity.RED:
                    severity = Severity.YELLOW
                state.follow_up_hours = 72

            elif classification == "possible_measles":
                treatments.append("POSSIBLE MEASLES: Give Vitamin A — 100,000 IU (age 6-11 months) or 200,000 IU (age 12-59 months). Single dose.")
                treatments.append("Give Paracetamol for fever. Keep child hydrated.")
                treatments.append("MEASLES with eye/mouth complications → REFER to health facility.")
                if not severity == Severity.RED:
                    severity = Severity.YELLOW
                state.follow_up_hours = 48

            elif classification == "severe_malnutrition":
                muac_text = f" (MUAC: {state.muac_mm}mm)" if state.muac_mm else ""
                treatments.append(f"SEVERE ACUTE MALNUTRITION (SAM){muac_text}: REFER IMMEDIATELY for therapeutic feeding.")
                treatments.append("Give sugar-water on the way to prevent hypoglycaemia.")
                treatments.append("Keep the child warm. Continue breastfeeding.")
                severity = Severity.RED
                state.referred = True
                state.follow_up_hours = 24

            elif classification == "moderate_malnutrition":
                muac_text = f" (MUAC: {state.muac_mm}mm)" if state.muac_mm else ""
                treatments.append(f"MODERATE ACUTE MALNUTRITION (MAM){muac_text}: Supplementary feeding program.")
                treatments.append("Feed 5-6 times daily. Add oil/groundnut paste to porridge.")
                treatments.append("Give deworming (Mebendazole) if not given in last 6 months.")
                if not severity == Severity.RED:
                    severity = Severity.YELLOW
                state.follow_up_hours = 336  # 14 days

        # Comorbidity warning: if multiple conditions, flag interaction
        if len([c for c in state.classifications if c != "unclassified"]) >= 2:
            conditions = ", ".join(c.replace("_", " ").title() for c in state.classifications)
            treatments.insert(0, f"⚠ MULTIPLE CONDITIONS: {conditions}. Treat the most urgent first. If in doubt → REFER.")
            if severity != Severity.RED:
                severity = Severity.YELLOW

        # Build triage result
        triage = TriageResult(
            severity=severity,
            red_flags=red_flags,
            manage_at_home=[t for t in treatments if "REFER" not in t],
            refer_reasons=[t for t in treatments if "REFER" in t],
            follow_up=f"Reassess in {state.follow_up_hours} hours" if state.follow_up_hours else None,
        )

        # Build response
        loc = state.locale
        if severity == Severity.RED:
            header = f"**{t('triage_refer_now', loc)}**\n\n"
        elif severity == Severity.YELLOW:
            header = f"**{t('triage_monitor', loc)}**\n\n"
        else:
            header = f"**{t('triage_manage_home', loc)}**\n\n"

        classification_text = ", ".join(
            c.replace("_", " ").title() for c in state.classifications
        )
        response = (
            f"{header}"
            f"**Classification:** {classification_text}\n"
            f"**Severity:** {severity.value.upper()}\n\n"
            f"**Treatment Plan:**\n"
            + "\n".join(f"- {t}" for t in treatments)
        )

        if state.follow_up_hours:
            response += f"\n\n**Follow up:** Reassess in {state.follow_up_hours} hours."

        # Retrieve supporting evidence from knowledge base
        if self._retriever and state.classifications:
            try:
                query_terms = " ".join(
                    c.replace("_", " ") for c in state.classifications if c != "unclassified"
                )
                if state.danger_signs_found:
                    query_terms += " danger signs " + " ".join(state.danger_signs_found[:2])
                hits = self._retriever.search(query=query_terms, top_k=2, mode_filter="vht")
                if hits:
                    response += "\n\n**Evidence (MoH Guidelines):**"
                    for i, hit in enumerate(hits[:2]):
                        source = hit.metadata.get("source", "MoH")
                        section = hit.metadata.get("section", "")
                        label = f"[{i+1}] {source}"
                        if section:
                            label += f" — {section}"
                        # Truncate passage to key sentences
                        snippet = hit.text[:200].rsplit(".", 1)[0] + "."
                        response += f"\n- **{label}**: {snippet}"
            except Exception:
                pass  # Don't fail treatment response if retrieval fails

        state.phase = TriagePhase.FOLLOW_UP

        return {
            "response": response,
            "phase": state.phase.value,
            "triage": triage,
            "follow_up_question": None,
            "assessment_complete": True,
        }

    def _handle_follow_up(self, state: TriageState, text: str) -> dict:
        """Phase 6: Post-assessment — answer follow-up questions or reset."""
        if any(w in text.lower() for w in ["new patient", "next patient", "reset", "start over"]):
            del self._sessions[next(k for k, v in self._sessions.items() if v is state)]
            return self._respond(
                TriageState(),
                "Ready for next patient. What symptoms does the patient have?",
            )

        return self._respond(
            state,
            "The assessment is complete. You can ask follow-up questions about this patient, "
            "or say **'next patient'** to start a new assessment.",
        )

    def _generate_assessment_question(self, state: TriageState) -> dict:
        """Generate the next assessment question based on what we know."""
        all_text = " ".join(state.symptoms_reported).lower()

        # Priority questions based on suspected condition
        if "fever" in all_text and "rdt" not in all_text:
            return self._respond(
                state,
                "The patient has fever. Have you done an **RDT (Rapid Diagnostic Test)** for malaria?\n"
                "What was the result? (positive / negative)",
                follow_up=True,
            )

        if ("cough" in all_text or "breathing" in all_text) and "respiratory_rate" not in state.vital_signs:
            return self._respond(
                state,
                "The patient has breathing problems. Please **count the breathing rate** "
                "for 1 FULL minute. How many breaths per minute?",
                follow_up=True,
            )

        if "diarrhoea" in all_text or "diarrhea" in all_text:
            questions = []
            if "blood" not in all_text:
                questions.append("Is there blood in the stool?")
            if "sunken" not in all_text:
                questions.append("Are the eyes sunken? Is the child thirsty?")
            if questions:
                return self._respond(state, "\n".join(questions), follow_up=True)

        # Generic follow-up
        return self._respond(
            state,
            "Any other symptoms? (fever, cough, diarrhoea, rash, swelling, pain, not eating?)\n"
            "Or say **'that's all'** if you've described everything.",
            follow_up=True,
        )

    def _generate_emergency_referral(self, state: TriageState, signs: list[str]) -> dict:
        """Generate immediate referral response for danger signs."""
        sign_list = "\n".join(f"- **{s}**" for s in signs)
        pre_referral = []

        all_text = " ".join(state.symptoms_reported).lower()
        if "fever" in all_text or "malaria" in all_text:
            pre_referral.append("Give rectal Artesunate if available (pre-referral for possible severe malaria)")
        if "convuls" in all_text or "seizure" in all_text:
            pre_referral.append("Give Diazepam rectal 0.5 mg/kg (max 10 mg)")
        if "dehydrat" in all_text or "diarrhoea" in all_text:
            pre_referral.append("Start ORS immediately if child can drink")

        pre_referral_text = "\n".join(f"- {t}" for t in pre_referral) if pre_referral else "- Keep the child warm\n- Continue breastfeeding if possible"

        triage = TriageResult(
            severity=Severity.RED,
            red_flags=[
                RedFlag(
                    symptom=s, severity=Severity.RED,
                    action=EscalationAction.EMERGENCY_REFER,
                    detail=f"General danger sign: {s}",
                )
                for s in state.danger_signs_found
            ],
            refer_reasons=state.danger_signs_found,
            follow_up="Follow up after referral to confirm patient reached facility.",
        )

        state.phase = TriagePhase.TREAT_REFER
        state.referred = True

        loc = state.locale
        return {
            "response": (
                f"{t('triage_danger_detected', loc)}\n\n"
                f"{sign_list}\n\n"
                f"**Pre-referral treatment:**\n{pre_referral_text}\n\n"
                f"{t('escalation_message', loc)}"
            ),
            "phase": state.phase.value,
            "triage": triage,
            "follow_up_question": None,
            "assessment_complete": True,
        }

    def _respond(
        self, state: TriageState, text: str, follow_up: bool = False
    ) -> dict:
        return {
            "response": text,
            "phase": state.phase.value,
            "triage": None,
            "follow_up_question": text if follow_up else None,
            "assessment_complete": False,
        }
