"""Mode supervisor — routes user queries to VHT / Maternal / Community mode.

Keyword-based classifier (no LLM call) for speed and offline resilience.
"""

from __future__ import annotations

import re
from app.agents.state import RouteDecision
from app.models import Mode, Severity

# ── Keyword banks ──────────────────────────────────────────────────────────

_VHT_KEYWORDS: set[str] = {
    # iCCM symptoms
    "malaria", "omusujja", "fever", "diarrhoea", "diarrhea", "ekiddukaano",
    "pneumonia", "cough", "okukola", "senyiga", "measles", "dehydration",
    "ors", "zinc", "act", "coartem", "amoxicillin", "rdt", "rapid test",
    "mrdt", "danger sign", "convulsion", "vomiting", "okusesema",
    "not eating", "not drinking", "chest indrawing", "fast breathing",
    "stridor", "unconscious", "lethargic", "stiff neck", "swollen feet",
    "bloody stool", "sunken eyes", "skin pinch", "muac", "malnutrition",
    "kwashiorkor", "marasmus", "wasting", "stunting", "underweight",
    "vitamin a", "deworming", "mebendazole", "albendazole",
    # VHT-specific
    "vht", "village health", "community health worker", "iccm",
    "home visit", "referral", "register", "treat at home",
    "health centre", "classify", "assess", "triage",
}

_MATERNAL_KEYWORDS: set[str] = {
    # Pregnancy & antenatal
    "pregnant", "olubuto", "pregnancy", "antenatal", "anc", "prenatal",
    "trimester", "weeks pregnant", "due date", "edd", "lmp",
    "morning sickness", "nausea", "okusesema", "swollen", "oedema",
    "pre-eclampsia", "eclampsia", "high blood pressure", "bp",
    "gestational diabetes", "ultrasound", "scan",
    # Danger signs in pregnancy
    "bleeding", "omusaayi", "vaginal bleeding", "headache", "blurred vision",
    "fits", "convulsions", "fever in pregnancy", "water breaking",
    "reduced movement", "baby not moving", "premature",
    # Labour & delivery
    "labour", "labor", "contractions", "delivery", "birth",
    "okuzaala", "midwife", "birth plan", "c-section", "cesarean",
    # Postnatal
    "postnatal", "postpartum", "pnc", "breastfeeding", "okuyonsa",
    "newborn", "omwana", "cord care", "umbilical", "jaundice",
    "kangaroo care", "immunization", "vaccination", "bcg", "opv",
    "exclusive breastfeeding", "colostrum", "mastitis",
    # Family planning
    "family planning", "contraception", "spacing", "iud", "implant",
    "depo", "injectable", "pills", "condom",
}

_COMMUNITY_KEYWORDS: set[str] = {
    # General symptoms
    "headache", "stomach", "pain", "injury", "wound", "burn",
    "skin rash", "itching", "allergy", "diabetes", "hypertension",
    "hiv", "aids", "tb", "tuberculosis", "cholera", "typhoid",
    "covid", "flu", "cold", "sore throat", "ear pain",
    # Medications & pharmacy
    "medicine", "drug", "tablet", "dose", "prescription", "pharmacy",
    "paracetamol", "panadol", "aspirin", "antibiotic",
    "medication reminder", "refill", "side effect",
    # Clinic & facilities
    "clinic", "hospital", "health centre", "nearest", "location",
    "ambulance", "emergency", "doctor", "nurse",
    # Self-care
    "diet", "nutrition", "exercise", "water", "hygiene", "sanitation",
    "mosquito net", "hand washing", "first aid",
}

# Red-flag symptom patterns that always trigger REFER NOW
_RED_FLAG_PATTERNS: list[tuple[str, str]] = [
    (r"convuls|fits|seizure", "Convulsions / seizures"),
    (r"unconscious|not responsive|lethargic", "Unconscious / unresponsive"),
    (r"severe bleed|heavy bleed|omusaayi mungi", "Severe bleeding"),
    (r"chest indraw", "Chest indrawing (severe pneumonia)"),
    (r"not able to (drink|eat|breastfeed)", "Unable to drink or eat"),
    (r"stiff neck", "Stiff neck (possible meningitis)"),
    (r"severe dehydrat", "Severe dehydration"),
    (r"high fever.*(child|baby|omwana)", "High fever in child"),
    (r"cord.*(red|swollen|pus|smell)", "Infected umbilical cord"),
    (r"baby.*(not breath|blue|cold|floppy)", "Newborn not breathing / cold"),
]


def classify(query: str, current_mode: Mode | None = None) -> RouteDecision:
    """Classify user query into a health mode with symptom detection."""
    q = query.lower().strip()
    tokens = set(re.findall(r"[a-z']+", q))

    # ── Check for red flags first ──────────────────────────────────────
    detected_red_flags: list[str] = []
    for pattern, label in _RED_FLAG_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            detected_red_flags.append(label)

    severity_hint = Severity.RED if detected_red_flags else None

    # ── Score each mode ────────────────────────────────────────────────
    vht_score = len(tokens & _VHT_KEYWORDS)
    mat_score = len(tokens & _MATERNAL_KEYWORDS)
    com_score = len(tokens & _COMMUNITY_KEYWORDS)

    # Phrase-level boosts (multi-word terms)
    if "village health" in q or "vht" in q or "iccm" in q:
        vht_score += 3
    if "pregnant" in q or "antenatal" in q or "postnatal" in q or "breastfeed" in q:
        mat_score += 3
    if "nearest clinic" in q or "medication reminder" in q:
        com_score += 2

    total = vht_score + mat_score + com_score
    if total == 0:
        # No health keywords — stay in current mode or default to community
        mode = current_mode or Mode.COMMUNITY
        return RouteDecision(
            mode=mode,
            confidence=0.3,
            severity_hint=severity_hint,
            detected_symptoms=detected_red_flags,
            clarification="I'll do my best to help. Could you describe your health concern in more detail?",
        )

    scores = {
        Mode.VHT: vht_score / total,
        Mode.MATERNAL: mat_score / total,
        Mode.COMMUNITY: com_score / total,
    }
    best_mode = max(scores, key=scores.get)  # type: ignore[arg-type]
    confidence = scores[best_mode]

    # If user explicitly set a mode, bias toward it
    if current_mode and scores.get(current_mode, 0) > 0.25:
        best_mode = current_mode
        confidence = max(confidence, scores[current_mode])

    return RouteDecision(
        mode=best_mode,
        confidence=round(confidence, 3),
        severity_hint=severity_hint,
        detected_symptoms=detected_red_flags,
    )
