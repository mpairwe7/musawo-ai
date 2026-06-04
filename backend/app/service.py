"""Musawo AI — Core health service orchestrator.

Pipeline: InputGuard → Supervisor → Cache → Retrieval → Abstention → LLM → OutputGuard
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Generator

from app.agents.supervisor import classify
from app.metrics import (
    record_query,
    record_triage,
    record_red_flag,
    record_abstention,
    record_escalation,
    record_confidence,
    record_lang_mismatch,
    observe_retrieval_latency,
    observe_llm_latency,
    observe_total_latency,
    set_active_sessions,
)
from app.agents.triage_agent import TriageAgent
from app.guardrails import InputGuard, OutputGuard, scan_retrieved_text
from app.llm import (
    format_passages,
    generate,
    is_ready as llm_is_ready,
    stream_tokens,
)
from app.models import (
    ChatRequest,
    ChatResponse,
    Citation,
    EscalationAction,
    Mode,
    RedFlag,
    Severity,
    TriageResult,
)
from app.corrective_rag import corrective_retrieve, needs_clarification
from app.query import rewrite as rewrite_query
from app.resilience import CircuitBreaker
from app.retriever import (
    HybridRetriever,
    build_citations,
    compute_faithfulness,
)

logger = logging.getLogger("musawo.service")

# LLM circuit breaker — prevents cascade failures when LLM is overloaded
_LLM_CIRCUIT = CircuitBreaker(
    name="llm",
    failure_threshold=3,
    reset_timeout=15.0,
    max_timeout=120.0,
)
audit_logger = logging.getLogger("musawo.audit")

# ── Config (centralized in app.config) ──────────────────────────────────────

from .config import settings

LLM_DEADLINE_SECONDS = settings.llm_inference_timeout
GROUNDING_THRESHOLD = settings.grounding_threshold
CLINICAL_SAFETY_THRESHOLD = settings.clinical_safety_threshold
SESSION_TTL = settings.session_ttl_seconds
MAX_SESSIONS = 5000
MAX_HISTORY = 40
HISTORY_WINDOW = 10  # Last 10 turn-pairs sent to LLM for deep context
LLM_WORKERS = settings.llm_workers
AUDIT_LOG_PATH = settings.audit_log_path

# Emergency contacts (Uganda)
EMERGENCY_CONTACTS = {
    "health_hotline": "0800 100 263 (toll-free)",
    "ambulance": "0800 911 911",
    "mental_health": "0800 100 263",
    "maternal_hotline": "0800 100 263",
}

# ── Audit trail (JSONL file for all health guidance given) ────────────────

import json as _json

# Configure audit logger to write to JSONL file
_audit_handler = logging.FileHandler(AUDIT_LOG_PATH, encoding="utf-8")
_audit_handler.setFormatter(logging.Formatter("%(message)s"))
audit_logger.addHandler(_audit_handler)
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False


def _audit_log(
    session_id: str,
    query: str,
    answer: str,
    mode: str,
    locale: str,
    confidence: float,
    faithfulness: float | None = None,
    escalation: bool = False,
    triage_severity: str | None = None,
    citations: int = 0,
) -> None:
    """Write an immutable audit record for every health guidance interaction.

    For clinical accountability and regulatory compliance (Uganda DPA).
    """
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session_id": session_id,
        "query": query[:500],       # Truncate for privacy
        "answer_preview": answer[:200],
        "mode": mode,
        "locale": locale,
        "confidence": round(confidence, 3),
        "faithfulness": round(faithfulness, 3) if faithfulness else None,
        "escalation": escalation,
        "triage_severity": triage_severity,
        "citations": citations,
    }
    try:
        audit_logger.info(_json.dumps(record, ensure_ascii=False))
    except Exception:
        pass  # Never let audit logging crash the main flow


def _clinical_safety_check(
    answer: str,
    faithfulness: float | None,
    hits_count: int,
    locale: str,
) -> tuple[str, bool]:
    """Clinical safety gate: block or flag responses with dangerously low grounding.

    Returns (answer, flagged) where flagged=True means the response
    was modified with a safety warning.
    """
    from app.i18n import t as _t

    # If no passages retrieved and no LLM confidence → block entirely
    if hits_count == 0 and (faithfulness is None or faithfulness < 0.1):
        return _t("abstention", locale), True

    # If faithfulness is below clinical safety threshold → add strong warning
    if faithfulness is not None and faithfulness < CLINICAL_SAFETY_THRESHOLD:
        warning = (
            "\n\n**⚠ " + _t("grounding_warning", locale) + "**"
        )
        answer += warning
        return answer, True

    return answer, False


# ── Local language → English keyword map for retrieval boost ──────────────
# Maps common Luganda, Runyankole, and Swahili health terms to English
# so the retriever can find relevant English-language passages.
_HEALTH_TERM_MAP: dict[str, str] = {
    # ── Luganda ──────────────────────────────────────────────────────
    # Symptoms
    "omusujja": "fever", "musujja": "fever", "omutwe": "headache",
    "nfudde": "headache pain", "ekiddukaano": "diarrhoea",
    "okufuuwa": "cough", "okukola": "cough", "okusesema": "vomiting",
    "okussa": "breathing", "okulumwa": "pain", "okufuba": "pneumonia",
    "senyiga": "flu cold", "akaloosa": "rash skin",
    "okubuguma": "swelling oedema", "okwekaliriza": "fatigue weakness",
    "okuzirika": "dizziness fainting", "okunyogoga": "nausea",
    "okusaamusaamu": "convulsions seizures fits", "okutuuka": "fits convulsions",
    "okugenda": "diarrhoea stool", "okunnyinyira": "itching",
    "okunyiinya": "shivering chills", "okubaaga": "bleeding",
    "okulwadde": "sick illness", "amazzi": "water dehydration",
    "okuzimbulukuka": "unconscious", "okweetagala": "tired fatigue",
    "ennyonta": "thirst dehydration", "enjala": "hunger malnutrition",
    "okubonabona": "suffering pain", "endwadde": "disease illness",
    # Body parts
    "omubiri": "body", "amaaso": "eyes", "amatu": "ears",
    "ennyindo": "nose", "akamwa": "mouth throat", "ekifuba": "chest lungs",
    "olubuto": "stomach pregnancy abdomen", "emibiri": "body",
    "ekigere": "leg foot", "omukono": "arm hand", "omugongo": "back spine",
    "omusaayi": "blood", "omwoyo": "heart", "ebibuno": "joints",
    "enku": "bones", "endiga": "kidney", "ekibumba": "liver",
    # Conditions
    "malaria": "malaria", "sukaari": "diabetes sugar",
    "pulesa": "blood pressure hypertension", "sifilisi": "syphilis STI",
    "mukenenya": "HIV AIDS", "kibonerezo": "TB tuberculosis",
    "kolera": "cholera", "kawumpuli": "measles", "kafubo": "pneumonia",
    "lukoseese": "anaemia", "obukoosookooso": "epilepsy seizures",
    "obuvune": "fracture broken bone",
    # Maternal & child
    "olubuto": "pregnancy", "okuzaala": "delivery birth labour",
    "omwana": "child baby", "abaana": "children",
    "okuyonsa": "breastfeeding", "amata": "breast milk",
    "okuwuna": "miscarriage abortion", "okusaana": "postpartum",
    "embuto": "pregnancy", "eddagala": "medicine drug treatment",
    "ekirungi": "healthy good", "obuzito": "weight growth",
    "okugezesa": "immunization vaccine", "zimbi": "immunization injection",
    # Actions & facilities
    "ddwaliro": "hospital clinic facility", "omusawo": "doctor health worker",
    "okukebera": "test check examine diagnosis", "okujjanjaba": "treat treatment",
    "okuyamba": "help refer", "okulya": "eating feeding nutrition",
    "okunywa": "drinking fluids ORS", "ekyambu": "wound injury burn",
    "ensimbi": "pill tablet", "obulamu": "health",
    "kubonero": "signs symptoms danger", "nnina": "i have",
    "olumbe": "death danger emergency",
    # Nutrition
    "emmere": "food nutrition diet", "ebinyeebwa": "groundnuts protein",
    "enva": "fruit vegetables", "obubuka": "porridge food",
    "endiisa": "feeding complementary", "bitookoli": "vitamin A",

    # ── Runyankole / Rukiga ──────────────────────────────────────────
    # Symptoms
    "omushuija": "fever", "okushaarira": "diarrhoea",
    "okukora": "cough", "okushuuha": "vomiting", "okuhuuha": "breathing",
    "okurwara": "sick illness pain", "okubabara": "pain suffering",
    "okushandaga": "convulsions seizures fits", "okuzirikira": "unconscious fainting",
    "okubikarika": "swelling oedema", "okushashara": "itching rash",
    "okuteera": "bleeding", "okuremwa": "weakness fatigue tired",
    "okuniga": "choking difficulty breathing", "okunyarara": "shivering chills",
    # Body parts
    "amaisho": "eyes", "amatu": "ears", "enshonga": "nose",
    "ekikoba": "skin", "eibara": "stomach abdomen",
    "omushija": "chest lungs", "enda": "pregnancy stomach womb",
    "amaguru": "legs feet", "emikono": "arms hands",
    "omugongo": "back spine", "eshagama": "blood",
    # Conditions
    "obuzibu": "problem danger emergency", "obulwaire": "disease illness",
    "oburwaire": "disease illness", "shukaari": "diabetes sugar",
    "puresa": "blood pressure hypertension", "korera": "cholera",
    "kahumpuli": "measles", "ruhara": "diarrhoea epidemic",
    # Maternal & child
    "okuzaara": "delivery birth labour", "enda": "pregnancy womb",
    "omwana": "child baby", "abaana": "children",
    "obuhaise": "health wellness", "irwariro": "hospital clinic facility",
    "omusawo": "doctor health worker", "okugonza": "breastfeeding",
    "amata": "breast milk", "okuhara": "miscarriage bleeding",
    # Actions
    "okwebaza": "check examine", "okujanjaba": "treat treatment",
    "okuyamba": "help refer", "okurya": "eating feeding",
    "okunywera": "drinking fluids", "ekironda": "wound injury",

    # ── Swahili ──────────────────────────────────────────────────────
    # Symptoms
    "homa": "fever", "kichwa": "headache", "kuharisha": "diarrhoea",
    "kikohozi": "cough", "kutapika": "vomiting", "kupumua": "breathing",
    "maumivu": "pain", "upele": "rash skin", "kuvimba": "swelling oedema",
    "uchovu": "fatigue weakness tired", "kizunguzungu": "dizziness",
    "kichefuchefu": "nausea", "degedege": "convulsions seizures fits",
    "kupoteza fahamu": "unconscious", "kutoka damu": "bleeding",
    "kuwashwa": "itching", "kutetemeka": "shivering chills",
    "kukohoa damu": "coughing blood TB", "kupungua uzito": "weight loss",
    "kiu": "thirst dehydration", "kukosa hamu": "loss of appetite",
    # Body parts
    "mwili": "body", "macho": "eyes", "masikio": "ears",
    "pua": "nose", "kinywa": "mouth throat", "kifua": "chest lungs",
    "tumbo": "stomach abdomen", "mguu": "leg foot", "mkono": "arm hand",
    "mgongo": "back spine", "damu": "blood", "moyo": "heart",
    "ngozi": "skin", "figo": "kidney", "ini": "liver",
    "ubongo": "brain", "mapafu": "lungs",
    # Conditions
    "malaria": "malaria", "kisukari": "diabetes sugar",
    "shinikizo": "blood pressure hypertension",
    "ukimwi": "HIV AIDS", "kifua kikuu": "TB tuberculosis",
    "kipindupindu": "cholera", "surua": "measles",
    "nimonia": "pneumonia", "upungufu wa damu": "anaemia",
    "kifafa": "epilepsy seizures", "uvimbe": "tumour swelling",
    "maambukizi": "infection", "minyoo": "worms deworming",
    # Maternal & child
    "mimba": "pregnancy", "kuzaa": "delivery birth labour",
    "mtoto": "child baby", "watoto": "children",
    "kunyonyesha": "breastfeeding", "maziwa": "breast milk",
    "kuharibika mimba": "miscarriage", "baada ya kuzaa": "postpartum",
    "uzazi": "family planning contraception", "kondo la nyuma": "placenta",
    # Actions & facilities
    "hospitali": "hospital clinic facility",
    "daktari": "doctor health worker", "muuguzi": "nurse midwife",
    "kupima": "test check examine diagnosis",
    "kutibu": "treat treatment", "rufaa": "refer referral",
    "chanjo": "vaccine immunization", "dawa": "medicine drug treatment",
    "dalili": "symptoms signs", "ugonjwa": "disease illness",
    "afya": "health", "lishe": "nutrition diet feeding",
    "jeraha": "wound injury burn", "kuchoma": "injection vaccine",
    "kituo cha afya": "health centre facility",
    "vidonge": "pills tablets medicine", "maji": "water fluids ORS",
}


import re as _re

# ── Stop-word set for keyword search ──────────────────────────────────────

_STOP_WORDS = frozenset(
    "a an the is are was were be been am do does did will would shall should "
    "can could may might must have has had of in on at to for with by from "
    "and or not no nor but so if then than that this these those it its i me "
    "my we our you your he she they them their what which who whom how when "
    "where why all each every any some".split()
)


def _keyword_search(
    query: str,
    retriever: Any,
    top_k: int = 2,
) -> list[Any]:
    """Keyword-only search with stop-word filtering for FAQ blending.

    Returns RetrievalHit objects from the retriever's keyword fallback.
    """
    query_tokens = set(query.lower().split()) - _STOP_WORDS
    if not query_tokens:
        return []
    cleaned = " ".join(query_tokens)
    return retriever._keyword_fallback(cleaned, top_k=top_k, mode_filter=None)


# ── Facility / location query detection ───────────────────────────────────
_FACILITY_QUERY_RE = _re.compile(
    r"(nearest|closest|where is|find.*(clinic|hospital|facility|health cent)|"
    r"how (do i|can i) (get to|find|reach)|location of|directions to|"
    r"nearby.*(clinic|hospital|facility)|"
    # Luganda
    r"ddwaliro.*(kumpi|rina|wa)|eddwaliro.*(kumpi|rina|wa)|"
    r"nsobola.*(okufuna|okugenda).*ddwaliro|"
    # Runyankole
    r"irwariro.*(hakuuhi|hari|hahi)|"
    # Swahili
    r"hospitali.*(karibu|iko wapi)|wapi.*hospitali|"
    r"kituo cha afya)",
    _re.I,
)


def _handle_facility_query(query: str, locale: str) -> str | None:
    """Detect and answer facility/location queries directly.

    Returns a helpful response about finding nearby clinics,
    or None if it's not a facility query.
    """
    if not _FACILITY_QUERY_RE.search(query):
        return None

    from app.i18n import t as _t

    responses = {
        "en": (
            "## Finding Your Nearest Health Facility\n\n"
            "To find the nearest health centre:\n\n"
            "1. **Use the Clinic Finder** — tap the 📍 pin icon in the header. "
            "It will use your GPS location to show nearby facilities sorted by distance.\n\n"
            "2. **Call the health hotline**: **0800 100 263** (toll-free, 24/7) — "
            "they can direct you to the nearest facility.\n\n"
            "3. **Ask your local VHT** (Village Health Team member) — "
            "they know all health facilities in your area.\n\n"
            "**Emergency?** If this is an emergency, go to the nearest Health Centre III or higher, "
            "or call **0800 911 911** for an ambulance.\n\n"
            "---\n*" + _t("disclaimer", "en") + "*"
        ),
        "lg": (
            "## Okufuna Eddwaliro Erisinga Okuba Okumpi\n\n"
            "Okufuna eddwaliro erisinga okuba okumpi:\n\n"
            "1. **Kozesa Clinic Finder** — nyiga akabonero ka 📍 mu mutwe gw'app. "
            "Ejja kukozesa GPS yo okulaga eddwaliro ezisinga okuba okumpi.\n\n"
            "2. **Yita ku simu y'obulamu**: **0800 100 263** (ya bwereere) — "
            "bajja kukuyamba okumanya eddwaliro erisinga okuba okumpi.\n\n"
            "3. **Buuza VHT wo** (omusomesa w'obulamu mu kitundu) — "
            "amanyi eddwaliro zonna mu kitundu kyo.\n\n"
            "**Mbeera y'amangu?** Genda mu ddwaliro erya Health Centre III oba waggulu, "
            "oba yita ku simu **0800 911 911** okufuna ambulansi.\n\n"
            "---\n*" + _t("disclaimer", "lg") + "*"
        ),
        "nyn": (
            "## Okushanga Irwariro Erisinga Okuba Hakuuhi\n\n"
            "Okushanga irwariro erisinga okuba hakuuhi:\n\n"
            "1. **Kozesa Clinic Finder** — nyiga akabonero ka 📍 omu mutwe gw'app.\n\n"
            "2. **Koroha esimu y'obuhaise**: **0800 100 263** (ya bure).\n\n"
            "3. **Buuza VHT wawe** — amanyire amawariro goona omu kicweka kyawe.\n\n"
            "**Ombeera y'amaani?** Genda omu irwariro erya Health Centre III nari waiguru, "
            "nari koroha **0800 911 911**.\n\n"
            "---\n*" + _t("disclaimer", "nyn") + "*"
        ),
        "sw": (
            "## Kupata Hospitali ya Karibu\n\n"
            "Kupata hospitali ya karibu:\n\n"
            "1. **Tumia Clinic Finder** — bonyeza alama ya 📍 kwenye kichwa cha app. "
            "Itatumia GPS yako kuonyesha hospitali za karibu.\n\n"
            "2. **Piga simu ya afya**: **0800 100 263** (bila malipo) — "
            "watakusaidia kupata hospitali ya karibu.\n\n"
            "3. **Uliza VHT wako** — anajua hospitali zote katika eneo lako.\n\n"
            "**Dharura?** Nenda hospitali ya Health Centre III au zaidi, "
            "au piga **0800 911 911** kwa ambulensi.\n\n"
            "---\n*" + _t("disclaimer", "sw") + "*"
        ),
    }
    return responses.get(locale, responses["en"])


def _detect_input_language(query: str) -> str | None:
    """Auto-detect input language. Sunbird AI ML detection is primary,
    keyword heuristic is fallback.

    Returns locale code ('lg', 'nyn', 'sw') or None if English/unknown.
    """
    # Primary: Sunbird AI ML-based language detection
    try:
        from app.sunbird import is_available, detect_language
        if is_available() and len(query.strip()) >= 3:
            result = detect_language(query)
            if result and result.get("locale") != "en":
                logger.info("Sunbird detected language: %s", result.get("locale"))
                return result["locale"]
            if result and result.get("locale") == "en":
                return None
    except Exception as e:
        logger.debug("Sunbird language detection failed, using fallback: %s", e)

    # Fallback: keyword heuristic (offline, always works)
    # Use ALL terms in the health term map, grouped by language
    lower = query.lower()
    _LG_TERMS = {
        "omusujja", "musujja", "omutwe", "ekiddukaano", "okufuuwa",
        "olubuto", "omwana", "ddwaliro", "eddagala", "nfudde", "nnina",
        "okuyonsa", "okusesema", "okulumwa", "amazzi", "obulamu",
        "abaana", "okuzaala", "embuto", "senyiga", "okufuba",
        "okubuguma", "okuzirika", "okusaamusaamu", "okulwadde",
        "okukebera", "akaloosa", "ekyambu", "emmere", "kubonero",
        "omusaayi", "sukaari", "pulesa", "omubiri", "ekifuba",
        "okugenda", "obuzito", "amata", "okuwuna",
    }
    _NYN_TERMS = {
        "omushuija", "okushaarira", "irwariro", "obuhaise", "okurwara",
        "okubabara", "enda", "okuzaara", "okukora", "okushuuha",
        "okuhuuha", "obulwaire", "obuzibu", "eshagama", "shukaari",
        "puresa", "okushandaga", "okuzirikira", "amaisho", "okugonza",
    }
    _SW_TERMS = {
        "homa", "kichwa", "kuharisha", "kikohozi", "hospitali", "mtoto",
        "dawa", "mimba", "dalili", "afya", "maumivu", "chanjo",
        "kutapika", "kupumua", "degedege", "kisukari", "shinikizo",
        "daktari", "maziwa", "kuzaa", "kunyonyesha", "upele",
        "watoto", "tumbo", "mwili", "damu", "ugonjwa", "jeraha",
    }

    lg_hits = sum(1 for t in _LG_TERMS if t in lower)
    nyn_hits = sum(1 for t in _NYN_TERMS if t in lower)
    sw_hits = sum(1 for t in _SW_TERMS if t in lower)
    best = max(lg_hits, nyn_hits, sw_hits)
    if best == 0:
        return None
    if lg_hits == best:
        return "lg"
    if nyn_hits == best:
        return "nyn"
    return "sw"


def _enrich_query_for_retrieval(query: str, locale: str) -> str:
    """Translate non-English queries to English for retrieval.

    Strategy:
    1. Sunbird neural translation → use ENGLISH ONLY for retrieval
       (mixed-language queries confuse the dense model)
    2. Keyword map → append English terms to original query
    """
    # Auto-detect language if locale is English but query is in local language
    if locale == "en":
        detected = _detect_input_language(query)
        if detected:
            locale = detected
        else:
            return query

    # Primary: Sunbird neural translation — return ENGLISH for retrieval
    # (not mixed original+translation, which confuses bge-m3)
    try:
        from app.sunbird import is_available, translate_to_english
        if is_available():
            translated = translate_to_english(query, locale)
            if translated and len(translated.strip()) > 3:
                logger.info("Sunbird translated [%s]: '%s' → '%s'",
                            locale, query[:50], translated[:50])
                # Return pure English translation for dense search
                return translated
    except Exception as e:
        logger.debug("Sunbird translation failed, using keyword fallback: %s", e)

    # Fallback: keyword map enrichment (offline, always works)
    lower = query.lower()
    english_terms: list[str] = []
    for term, eng in _HEALTH_TERM_MAP.items():
        if term in lower:
            english_terms.append(eng)
    if not english_terms:
        return query
    return f"{query} ({' '.join(english_terms)})"


# ── Session store ──────────────────────────────────────────────────────────

@dataclass
class Session:
    history: deque = field(default_factory=lambda: deque(maxlen=MAX_HISTORY))
    created: float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)
    mode: Mode = Mode.COMMUNITY
    pregnancy_week: int | None = None


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()
        self._last_cleanup = time.monotonic()

    def _cleanup_expired(self) -> int:
        """Remove sessions that exceeded TTL. Called under lock."""
        now = time.monotonic()
        # Only run cleanup every 60 seconds
        if now - self._last_cleanup < 60:
            return 0
        self._last_cleanup = now
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.last_active > SESSION_TTL
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.info("TTL cleanup: removed %d expired sessions", len(expired))
        return len(expired)

    def get_or_create(self, session_id: str | None) -> tuple[str, Session]:
        with self._lock:
            # Periodic TTL cleanup
            self._cleanup_expired()

            if not session_id:
                session_id = str(uuid.uuid4())

            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.last_active = time.monotonic()
                return session_id, session

            # Capacity eviction — evict oldest 10% (not 25%) to reduce data loss
            if len(self._sessions) >= MAX_SESSIONS:
                stale = sorted(
                    self._sessions.items(),
                    key=lambda x: x[1].last_active,
                )
                evict_count = max(len(stale) // 10, 1)
                for sid, _ in stale[:evict_count]:
                    del self._sessions[sid]
                logger.warning(
                    "Session capacity eviction: removed %d oldest sessions (%d total)",
                    evict_count, len(self._sessions),
                )

            session = Session()
            self._sessions[session_id] = session
            return session_id, session

    def update_session(self, session_id: str, mode: Mode | None = None,
                       pregnancy_week: int | None = None,
                       history_entry: dict | None = None) -> None:
        """Thread-safe session mutation."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            if mode is not None:
                session.mode = mode
            if pregnancy_week is not None:
                session.pregnancy_week = pregnancy_week
            if history_entry is not None:
                session.history.append(history_entry)

    def get_history(self, session_id: str, window: int = HISTORY_WINDOW) -> list[dict]:
        """Thread-safe history read."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return []
            return list(session.history)[-window * 2:]


# ── Health Service ─────────────────────────────────────────────────────────

class HealthService:
    """Main orchestrator for Musawo health guidance pipeline."""

    def __init__(self) -> None:
        self.retriever = HybridRetriever()
        self.sessions = SessionStore()
        self.triage_agent = TriageAgent(retriever=self.retriever)
        self._executor = ThreadPoolExecutor(max_workers=LLM_WORKERS)
        self._ready = False

    # Common health queries to pre-warm the retrieval cache at startup
    _WARMUP_QUERIES = [
        "malaria prevention mosquito net",
        "danger signs pregnancy",
        "ORS zinc diarrhoea dosage",
        "breastfeeding newborn colostrum",
        "immunization vaccine schedule children",
        "HIV ART treatment adherence",
        "pneumonia cough fast breathing child",
        "fever child malaria RDT",
        "family planning contraception",
        "first aid burn wound bleeding",
    ]

    def initialize(self) -> None:
        """Warm up retriever, verify LLM, and pre-warm cache."""
        retriever_ok = self.retriever.initialize()
        llm_ok = llm_is_ready()
        self._ready = True
        logger.info(
            "HealthService initialized (retriever=%s, llm=%s)",
            retriever_ok,
            llm_ok,
        )

        # Pre-warm retrieval cache with common queries (background)
        if retriever_ok:
            try:
                for q in self._WARMUP_QUERIES:
                    self.retriever.search(query=q, top_k=4, mode_filter=None)
                logger.info("Pre-warmed retrieval cache with %d queries", len(self._WARMUP_QUERIES))
            except Exception as e:
                logger.debug("Cache warmup failed (non-critical): %s", e)

    @property
    def is_ready(self) -> bool:
        return self._ready

    def generate(self, req: ChatRequest) -> ChatResponse:
        """Synchronous health guidance generation."""
        from app.i18n import t as _t
        record_query(req.mode.value, req.locale.value)

        # 1. Input guard
        guard = InputGuard.check(req.query, req.locale.value)
        if not guard.allowed:
            return ChatResponse(
                answer=guard.reason,
                mode=req.mode,
                locale=req.locale,
                confidence=0.0,
                escalation_required="crisis" in (guard.flags or []),
                escalation_message=guard.reason if "crisis" in (guard.flags or []) else None,
            )

        # 2. Session (thread-safe)
        session_id, session = self.sessions.get_or_create(req.session_id)
        self.sessions.update_session(session_id, mode=req.mode, pregnancy_week=req.pregnancy_week)
        set_active_sessions(len(self.sessions._sessions))

        # 2b. Facility query shortcut (don't waste retrieval on location questions)
        facility_answer = _handle_facility_query(req.query, req.locale.value)
        if facility_answer:
            return ChatResponse(
                answer=facility_answer,
                mode=req.mode,
                locale=req.locale,
                confidence=1.0,
                session_id=session_id,
            )

        # 3. Supervisor routing
        route = classify(req.query, current_mode=req.mode)
        effective_mode = route.mode

        # 3b. Query rewriting — normalise abbreviations, fix typos, resolve coreferences
        history = self._get_history(req.session_id) if hasattr(self, '_get_history') else []
        rewritten = rewrite_query(req.query, history=history or None)
        if rewritten != req.query:
            logger.debug("Query rewrite: '%s' → '%s'", req.query[:50], rewritten[:50])

        # 4. Retrieval — dual-search for multilingual queries
        search_query = _enrich_query_for_retrieval(rewritten, req.locale.value)
        with observe_retrieval_latency():
            hits = self.retriever.search(
                query=search_query,
                top_k=4,
                mode_filter=effective_mode.value,
            )

            # Dual-search: if enriched query differs from original (translation happened),
            # also search with original query and merge best results via score
            if search_query != req.query and req.locale.value != "en":
                orig_hits = self.retriever.search(
                    query=req.query, top_k=4, mode_filter=effective_mode.value,
                )
                # Merge: keep best unique passages by text hash
                seen = {h.text[:100] for h in hits}
                for oh in orig_hits:
                    if oh.text[:100] not in seen:
                        hits.append(oh)
                        seen.add(oh.text[:100])
                hits.sort(key=lambda h: h.score, reverse=True)
                hits = hits[:4]

            # Cross-mode fallback if results are weak
            best_hit_score = max((h.score for h in hits), default=0)
            if len(hits) < 2 or best_hit_score < 0.3:
                all_hits = self.retriever.search(query=search_query, top_k=4, mode_filter=None)
                if all_hits and max((h.score for h in all_hits), default=0) > best_hit_score:
                    hits = all_hits

        # Scrub retrieved passages for indirect injection
        for hit in hits:
            hit.text, _ = scan_retrieved_text(hit.text)

        # 4b. Corrective RAG — re-retrieve if quality is low
        if hits and self.retriever.is_ready:
            try:
                hit_dicts = [{"text": h.text, "source": h.metadata.get("source", ""), "score_rrf": h.score} for h in hits]
                corrected_dicts, was_corrected = corrective_retrieve(
                    rewritten, self.retriever, hit_dicts, top_k=4
                )
                if was_corrected:
                    logger.info("Corrective RAG improved retrieval quality")
            except Exception:
                logger.debug("Corrective RAG skipped", exc_info=True)

        # 4b-2. Blend top FAQ keyword hits after corrective RAG
        try:
            kw_hits = _keyword_search(rewritten, self.retriever, top_k=2)
            if kw_hits:
                seen_texts = {h.text[:100] for h in hits}
                for kh in kw_hits:
                    if kh.text[:100] not in seen_texts:
                        hits.append(kh)
                        seen_texts.add(kh.text[:100])
        except Exception:
            logger.debug("FAQ keyword blend skipped", exc_info=True)

        # 4c. Clarification check — ask for more detail if query is ambiguous
        hit_dicts_for_check = [{"text": h.text, "source": h.metadata.get("source", "")} for h in hits]
        clarification = needs_clarification(req.query, hit_dicts_for_check)
        if clarification:
            return ChatResponse(
                answer=clarification,
                sources=[],
                citations=[],
                faithfulness_score=None,
                retrieval_mode="clarification",
                mode=effective_mode,
                locale=req.locale,
                escalation_required=False,
            )

        # 5. Abstention check
        best_score = max((h.score for h in hits), default=0.0)
        record_confidence(req.locale.value, best_score)
        if OutputGuard.should_abstain(best_score if hits else None, len(hits)):
            record_abstention(req.locale.value)
            from app.i18n import t as _t
            loc = req.locale.value
            return ChatResponse(
                answer=_t("abstention", loc),
                mode=effective_mode,
                locale=req.locale,
                confidence=0.0,
                escalation_required=True,
                escalation_message=_t("low_confidence", loc),
                session_id=session_id,
            )

        # 6. Build history for LLM (thread-safe read)
        history_msgs = self.sessions.get_history(session_id)

        # 7. LLM generation with deadline
        passages = [
            {"text": h.text, "source": h.metadata.get("source", "MoH"), "section": h.metadata.get("section", "")}
            for h in hits
        ]

        try:
            with observe_llm_latency():
                future = self._executor.submit(
                    generate,
                    query=req.query,
                    passages=passages,
                    mode=effective_mode.value,
                    history=history_msgs,
                    locale=req.locale.value,
                )
                result = future.result(timeout=LLM_DEADLINE_SECONDS)
                answer_text = result["text"]
        except TimeoutError:
            logger.warning("LLM timed out after %ds", LLM_DEADLINE_SECONDS)
            from app.i18n import t as _t
            loc = req.locale.value
            answer_text = (
                f"{_t('llm_timeout', loc)}\n\n"
                f"{hits[0].text if hits else _t('escalation_message', loc)}"
            )
        except Exception as e:
            logger.error("LLM generation failed: %s", e)
            from app.i18n import t as _t
            answer_text = _t("llm_error", req.locale.value)

        # 8. Output guards
        loc = req.locale.value
        answer_text = OutputGuard.redact_pii(answer_text)
        answer_text = OutputGuard.sanitize(answer_text)

        if OutputGuard.check_prompt_leakage(answer_text):
            from app.i18n import t as _t
            answer_text = _t("prompt_leakage", loc)

        # 9. Grounding + Clinical Safety Gate
        contexts = [h.text for h in hits]
        faithfulness = compute_faithfulness(answer_text, contexts)
        answer_text, safety_flagged = _clinical_safety_check(
            answer_text, faithfulness, len(hits), loc
        )
        if not safety_flagged:
            answer_text = OutputGuard.check_grounding(answer_text, faithfulness, loc)
        answer_text = OutputGuard.enforce_disclaimer(answer_text, loc)

        # 10. Triage (VHT mode)
        triage = None
        triage_sev = None
        if effective_mode == Mode.VHT:
            triage = self._build_triage(route, hits)
            if triage:
                triage_sev = triage.severity.value
                record_triage(triage_sev)
                for rf in (triage.red_flags or []):
                    record_red_flag(rf.symptom)

        # 11. Escalation check
        escalation = OutputGuard.should_escalate(faithfulness, len(hits))
        if route.detected_symptoms:
            escalation = True
        if safety_flagged:
            escalation = True
        if escalation:
            record_escalation(req.locale.value)

        # 12. Citations
        citations = [
            Citation(**c) for c in build_citations(hits)
        ]

        conf = round(min(best_score, faithfulness) if faithfulness else best_score, 3)

        # 13. Audit trail (immutable log of every health guidance interaction)
        _audit_log(
            session_id=session_id,
            query=req.query,
            answer=answer_text,
            mode=effective_mode.value,
            locale=loc,
            confidence=conf,
            faithfulness=faithfulness,
            escalation=escalation,
            triage_severity=triage_sev,
            citations=len(citations),
        )

        # 14. Update session history (thread-safe)
        self.sessions.update_session(session_id, history_entry={"role": "user", "content": req.query})
        self.sessions.update_session(session_id, history_entry={"role": "assistant", "content": answer_text})

        return ChatResponse(
            answer=answer_text,
            mode=effective_mode,
            locale=req.locale,
            confidence=conf,
            citations=citations,
            faithfulness_score=round(faithfulness, 3) if faithfulness else None,
            triage=triage,
            escalation_required=escalation,
            escalation_message=(
                _t("escalation_message", loc) if escalation else None
            ),
            session_id=session_id,
        )

    def stream_response(self, req: ChatRequest) -> Generator[dict[str, Any], None, None]:
        """SSE streaming response generator."""
        # Input guard
        guard = InputGuard.check(req.query, req.locale.value)
        if not guard.allowed:
            yield {"event": "error", "data": guard.reason}
            return

        session_id, _ = self.sessions.get_or_create(req.session_id)
        self.sessions.update_session(session_id, mode=req.mode)

        # Facility query shortcut
        facility_answer = _handle_facility_query(req.query, req.locale.value)
        if facility_answer:
            yield {"event": "metadata", "data": {"mode": req.mode.value, "citations": [], "session_id": session_id, "triage": None, "red_flags": []}}
            yield {"event": "data", "data": facility_answer}
            yield {"event": "done", "data": ""}
            return

        route = classify(req.query, current_mode=req.mode)
        effective_mode = route.mode

        search_query = _enrich_query_for_retrieval(req.query, req.locale.value)
        hits = self.retriever.search(
            query=search_query, top_k=4, mode_filter=effective_mode.value
        )
        for hit in hits:
            hit.text, _ = scan_retrieved_text(hit.text)

        best_score = max((h.score for h in hits), default=0.0)
        citations = build_citations(hits)

        # Metadata event
        triage = None
        if effective_mode == Mode.VHT:
            triage = self._build_triage(route, hits)

        yield {
            "event": "metadata",
            "data": {
                "mode": effective_mode.value,
                "citations": citations,
                "session_id": session_id,
                "triage": triage.model_dump() if triage else None,
                "red_flags": route.detected_symptoms,
            },
        }

        # Abstention
        if OutputGuard.should_abstain(best_score if hits else None, len(hits)):
            from app.i18n import t as _t
            msg = _t("abstention", req.locale.value)
            yield {"event": "data", "data": msg}
            yield {"event": "done", "data": ""}
            return

        # Stream tokens
        passages = [
            {"text": h.text, "source": h.metadata.get("source", "MoH"), "section": h.metadata.get("section", "")}
            for h in hits
        ]
        history_msgs = self.sessions.get_history(session_id)

        full_answer = ""
        for chunk in stream_tokens(
            query=req.query,
            passages=passages,
            mode=effective_mode.value,
            history=history_msgs,
            locale=req.locale.value,
        ):
            if chunk["type"] == "token":
                full_answer += chunk["text"]
                yield {"event": "data", "data": chunk["text"]}
            elif chunk["type"] == "done":
                break

        # Post-stream grounding
        contexts = [h.text for h in hits]
        faithfulness = compute_faithfulness(full_answer, contexts)
        escalation = OutputGuard.should_escalate(faithfulness, len(hits))

        yield {
            "event": "grounding",
            "data": {
                "faithfulness_score": round(faithfulness, 3),
                "grounding_warning": faithfulness < GROUNDING_THRESHOLD,
                "escalation_required": escalation or bool(route.detected_symptoms),
            },
        }

        # Update session (thread-safe)
        self.sessions.update_session(session_id, history_entry={"role": "user", "content": req.query})
        self.sessions.update_session(session_id, history_entry={"role": "assistant", "content": full_answer})

        yield {"event": "done", "data": ""}

    def _build_triage(self, route, hits) -> TriageResult | None:
        """Build VHT triage result from routing and retrieval."""
        if not route.detected_symptoms:
            return TriageResult(
                severity=route.severity_hint or Severity.GREEN,
                manage_at_home=["Follow standard iCCM assessment protocol."],
            )

        red_flags = [
            RedFlag(
                symptom=symptom,
                severity=Severity.RED,
                action=EscalationAction.EMERGENCY_REFER,
                detail=f"Danger sign detected: {symptom}. Refer immediately.",
            )
            for symptom in route.detected_symptoms
        ]

        return TriageResult(
            severity=Severity.RED,
            red_flags=red_flags,
            refer_reasons=route.detected_symptoms,
            follow_up="Reassess within 24 hours if referred patient returns.",
        )
