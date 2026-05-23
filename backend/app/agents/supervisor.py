"""Mode supervisor — routes user queries to VHT / Maternal / Community mode.

Keyword-based classifier (no LLM call) for speed and offline resilience.
"""

from __future__ import annotations

import re
from app.agents.state import RouteDecision
from app.models import Mode, Severity

# ── Keyword banks ──────────────────────────────────────────────────────────

_VHT_KEYWORDS: set[str] = {
    # iCCM symptoms (English)
    "malaria", "fever", "diarrhoea", "diarrhea", "pneumonia", "cough",
    "measles", "dehydration", "ors", "zinc", "act", "coartem",
    "amoxicillin", "rdt", "rapid test", "mrdt", "danger sign",
    "convulsion", "vomiting", "not eating", "not drinking",
    "chest indrawing", "fast breathing", "stridor", "unconscious",
    "lethargic", "stiff neck", "swollen feet", "bloody stool",
    "sunken eyes", "skin pinch", "muac", "malnutrition",
    "kwashiorkor", "marasmus", "wasting", "stunting", "underweight",
    "vitamin a", "deworming", "mebendazole", "albendazole",
    # Luganda
    "omusujja", "musujja", "ekiddukaano", "okukola", "okufuuwa",
    "senyiga", "okusesema", "okusaamusaamu", "okulwadde",
    # Runyankole
    "omushuija", "okushaarira", "okukora", "okushuuha", "okushandaga",
    # Swahili
    "homa", "kuharisha", "kikohozi", "kutapika", "degedege",
    # VHT-specific
    "vht", "village health", "community health worker", "iccm",
    "home visit", "referral", "register", "treat at home",
    "health centre", "classify", "assess", "triage",
    "okulambula",  # Luganda: triage/assess
}

_MATERNAL_KEYWORDS: set[str] = {
    # Pregnancy & antenatal (English)
    "pregnant", "pregnancy", "antenatal", "anc", "prenatal",
    "trimester", "weeks pregnant", "due date", "edd", "lmp",
    "morning sickness", "nausea", "swollen", "oedema",
    "pre-eclampsia", "eclampsia", "high blood pressure", "bp",
    "gestational diabetes", "ultrasound", "scan",
    # Danger signs in pregnancy
    "bleeding", "vaginal bleeding", "headache", "blurred vision",
    "fits", "convulsions", "fever in pregnancy", "water breaking",
    "reduced movement", "baby not moving", "premature",
    # Labour & delivery
    "labour", "labor", "contractions", "delivery", "birth",
    "midwife", "birth plan", "c-section", "cesarean",
    # Postnatal
    "postnatal", "postpartum", "pnc", "breastfeeding",
    "newborn", "cord care", "umbilical", "jaundice",
    "kangaroo care", "immunization", "vaccination", "bcg", "opv",
    "exclusive breastfeeding", "colostrum", "mastitis",
    # Family planning
    "family planning", "contraception", "spacing", "iud", "implant",
    "depo", "injectable", "pills", "condom",
    # Luganda
    "olubuto", "embuto", "okuzaala", "okuyonsa", "omusaayi",
    "omwana", "amata", "okuwuna", "okusesema", "obuzito",
    "okugezesa",  # immunization
    # Runyankole
    "enda", "okuzaara", "okugonza", "okuhara", "eshagama",
    # Swahili
    "mimba", "kuzaa", "kunyonyesha", "uzazi", "mtoto",
    "maziwa", "chanjo", "kuharibika",
}

_COMMUNITY_KEYWORDS: set[str] = {
    # General symptoms (English)
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
    # Luganda
    "ddwaliro", "omusawo", "eddagala", "obulamu", "okulumwa",
    "omutwe", "sukaari", "pulesa", "akaloosa", "ekyambu",
    "nfudde", "emmere", "amazzi",
    # Runyankole
    "irwariro", "obuhaise", "obulwaire", "okurwara", "okubabara",
    "shukaari", "puresa",
    # Swahili
    "hospitali", "daktari", "dawa", "afya", "maumivu",
    "kichwa", "kisukari", "shinikizo", "upele", "lishe",
}

# Red-flag symptom patterns that always trigger REFER NOW
# Includes English, Luganda (lg), Runyankole (nyn), and Swahili (sw)
_RED_FLAG_PATTERNS: list[tuple[str, str]] = [
    # Convulsions / seizures
    (r"convuls|fits|seizure|okusaamusaamu|okutuuka|okushandaga|degedege|kifafa",
     "Convulsions / seizures"),
    # Unconscious / unresponsive
    (r"unconscious|not responsive|lethargic|okuzimbulukuka|okuzirikira|kupoteza fahamu|fahamu",
     "Unconscious / unresponsive"),
    # Severe bleeding
    (r"severe bleed|heavy bleed|omusaayi mungi|okubaaga nnyo|okuteera ennyo|kutoka damu nyingi",
     "Severe bleeding"),
    # Chest indrawing (severe pneumonia)
    (r"chest indraw|ekifuba kyeyongera|kifua kinaingia",
     "Chest indrawing (severe pneumonia)"),
    # Unable to drink or eat
    (r"not able to (drink|eat|breastfeed)|tayinza ku(nywa|lya|yonsa)|tarikubashor[ai].*ku(rya|nywera)|hawezi ku(nywa|la|nyonyesha)",
     "Unable to drink or eat"),
    # Stiff neck
    (r"stiff neck|ensingo enkakanyavu|shingo ngumu",
     "Stiff neck (possible meningitis)"),
    # Severe dehydration
    (r"severe dehydrat|amazzi gaggwaawo|okunyweerwa|upungufu mkubwa wa maji",
     "Severe dehydration"),
    # High fever in child
    (r"high fever.*(child|baby|omwana|mtoto)|omusujja.*(mungi|munene).*omwana|homa kali.*mtoto",
     "High fever in child"),
    # Infected umbilical cord
    (r"cord.*(red|swollen|pus|smell)|olukoba.*(mubisi|bivunda)|kitovu.*(uvimbe|usaha|harufu)",
     "Infected umbilical cord"),
    # Newborn not breathing
    (r"baby.*(not breath|blue|cold|floppy)|omwana.*(tassa|buludde|muyiiye)|mtoto.*(hapumui|baridi|bluu)",
     "Newborn not breathing / cold"),
    # Vaginal bleeding in pregnancy (all languages)
    (r"(vaginal|olubuto|enda|mimba).*(bleed|omusaayi|eshagama|damu)|omusaayi.*(olubuto|embuto)|damu.*mimba",
     "Vaginal bleeding in pregnancy"),
    # Severe abdominal pain
    (r"severe.*(abdom|stomach)|olubuto.*(bulumi|lumwa) nnyo|tumbo.*maumivu makali|eibara.*rikubabaza ennyo",
     "Severe abdominal pain"),
    # Suicide / self-harm (all languages)
    (r"suicide|kill myself|want to die|okwett[ai]|njagala okufa|kujiua|kutaka kufa",
     "Suicide / self-harm crisis"),
]


def classify(query: str, current_mode: Mode | None = None) -> RouteDecision:
    """Classify user query into a health mode with symptom detection."""
    q = query.lower().strip()
    tokens = set(re.findall(r"[a-z']+", q))

    # ── Check for red flags first (with negation awareness) ─────────────
    _negation_re = re.compile(
        r"\b(no|not|never|without|hasn't|don't|does not|didn't"
        r"|tewali|talina|hakuna|hana|si)\b", re.I,
    )
    detected_red_flags: list[str] = []
    for pattern, label in _RED_FLAG_PATTERNS:
        match = re.search(pattern, q, re.IGNORECASE)
        if match:
            # Check for negation within 4 words before the match
            prefix = q[:match.start()].strip()
            last_words = " ".join(prefix.split()[-4:]) if prefix else ""
            if _negation_re.search(last_words):
                continue  # Negated — skip this red flag
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
