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


# ── Danger sign patterns (hard-coded, no LLM needed) ──────────────────

GENERAL_DANGER_SIGNS = {
    "unable to drink or breastfeed": r"(not|unable|can.?t)\s*(drink|breastfeed|eat|feed|suckle)",
    "vomiting everything": r"vomit(s|ing)?\s*(everything|all)",
    "convulsions": r"convuls|fits|seizure|jerking",
    "lethargic or unconscious": r"(lethargic|unconscious|drowsy|very\s*sleepy|not\s*responsive|cannot\s*wake)",
    "chest indrawing": r"chest\s*(indraw|in-draw|retract)",
    "severe bleeding": r"(severe|heavy|lot\s*of)\s*bleed",
    "high fever in infant": r"(high|very)\s*fever.*(baby|infant|newborn|child)",
    "stiff neck": r"stiff\s*neck",
    "bulging fontanelle": r"bulg(ing|ed)\s*fontanel",
    "severe malnutrition": r"(severe|very)\s*(maln|wast|thin|swollen\s*feet)",
}

# ── Symptom classification rules (iCCM decision tree) ─────────────────

MALARIA_INDICATORS = {
    "fever", "hot body", "omusujja", "chills", "rigors", "sweating",
    "headache", "body pain", "joint pain", "vomiting",
}

PNEUMONIA_INDICATORS = {
    "cough", "difficult breathing", "fast breathing", "noisy breathing",
    "chest pain", "wheeze", "stridor", "okukola",
}

DIARRHOEA_INDICATORS = {
    "diarrhoea", "diarrhea", "loose stool", "watery stool", "blood in stool",
    "ekiddukaano", "vomiting", "dehydration", "sunken eyes",
}

# ── Breathing rate thresholds (iCCM protocol) ─────────────────────────

FAST_BREATHING_THRESHOLD = {
    # age_months: breaths_per_minute
    (2, 11): 50,    # 2-11 months: ≥50
    (12, 59): 40,   # 12-59 months: ≥40
}


class TriageAgent:
    """Stateful agent that guides VHTs through iCCM assessment."""

    def __init__(self):
        from threading import Lock
        self._sessions: dict[str, TriageState] = {}
        self._lock = Lock()

    def get_or_create_state(self, session_id: str) -> TriageState:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = TriageState()
            return self._sessions[session_id]

    def process(self, session_id: str, user_input: str) -> dict[str, Any]:
        """Process user input and return agent response with next action.

        Returns dict with:
        - response: str (agent's response text)
        - phase: str (current triage phase)
        - triage: TriageResult | None
        - follow_up_question: str | None
        - assessment_complete: bool
        """
        state = self.get_or_create_state(session_id)
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

    def _check_danger_signs(self, text: str, state: TriageState) -> list[str]:
        """Check for danger signs in user input. Returns newly found signs."""
        newly_found = []
        for sign_name, pattern in GENERAL_DANGER_SIGNS.items():
            if re.search(pattern, text, re.I) and sign_name not in state.danger_signs_found:
                state.danger_signs_found.append(sign_name)
                newly_found.append(sign_name)
        return newly_found

    def _handle_initial(self, state: TriageState, text: str) -> dict:
        """Phase 1: Get main complaint and patient age."""
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

        state.phase = TriagePhase.DANGER_CHECK

        questions = []
        if state.patient_age_months is None:
            questions.append("How old is the patient? (months or years)")

        questions.append(
            "I need to check for danger signs first. "
            "Can the child drink or breastfeed? "
            "Has the child had convulsions? "
            "Is the child lethargic or unconscious?"
        )

        return self._respond(
            state,
            f"I understand — the patient has: **{state.main_complaint}**.\n\n"
            f"Let me assess step by step.\n\n"
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

        # If we have enough info or hit max questions → classify
        if state.questions_asked >= state.max_questions or self._has_enough_info(state):
            state.phase = TriagePhase.CLASSIFY
            return self._handle_classify(state)

        return self._generate_assessment_question(state)

    def _has_enough_info(self, state: TriageState) -> bool:
        """Check if we have enough symptoms to classify."""
        all_text = " ".join(state.symptoms_reported).lower()
        malaria_score = len(MALARIA_INDICATORS & set(re.findall(r"\w+", all_text)))
        pneumonia_score = len(PNEUMONIA_INDICATORS & set(re.findall(r"\w+", all_text)))
        diarrhoea_score = len(DIARRHOEA_INDICATORS & set(re.findall(r"\w+", all_text)))
        return max(malaria_score, pneumonia_score, diarrhoea_score) >= 2

    def _handle_classify(self, state: TriageState) -> dict:
        """Phase 4: Classify based on gathered symptoms."""
        all_text = " ".join(state.symptoms_reported).lower()
        tokens = set(re.findall(r"\w+", all_text))

        # Score each condition
        malaria_score = len(MALARIA_INDICATORS & tokens)
        pneumonia_score = len(PNEUMONIA_INDICATORS & tokens)
        diarrhoea_score = len(DIARRHOEA_INDICATORS & tokens)

        classifications = []
        if malaria_score >= 2:
            classifications.append("possible_malaria")
        if pneumonia_score >= 2:
            classifications.append("possible_pneumonia")
        if diarrhoea_score >= 2:
            classifications.append("diarrhoea")

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
                else:
                    severity = Severity.YELLOW
                state.follow_up_hours = 72

        # Build triage result
        triage = TriageResult(
            severity=severity,
            red_flags=red_flags,
            manage_at_home=[t for t in treatments if "REFER" not in t],
            refer_reasons=[t for t in treatments if "REFER" in t],
            follow_up=f"Reassess in {state.follow_up_hours} hours" if state.follow_up_hours else None,
        )

        # Build response
        header = "**ASSESSMENT COMPLETE**\n\n"
        if severity == Severity.RED:
            header = "**REFER NOW — DANGER SIGNS DETECTED**\n\n"
        elif severity == Severity.YELLOW:
            header = "**CLASSIFICATION COMPLETE — TREAT AND MONITOR**\n\n"

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

        return {
            "response": (
                f"**DANGER SIGNS DETECTED — REFER IMMEDIATELY**\n\n"
                f"The following danger signs were found:\n{sign_list}\n\n"
                f"**Pre-referral treatment:**\n{pre_referral_text}\n\n"
                f"**Write a referral note** with: patient name, age, symptoms, "
                f"danger signs, treatment given, time of referral.\n\n"
                f"**Call the health facility** to alert them: **0800 100 263**\n\n"
                f"Transport the patient IMMEDIATELY."
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
