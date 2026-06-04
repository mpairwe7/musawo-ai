"""Musawo AI — SMS/USSD Gateway via Twilio.

Provides health guidance via:
- SMS: Question-answer via text message (Twilio)
- USSD: Interactive menu for feature phones (menu tree)

Most VHTs in rural Uganda use feature phones, not smartphones.
This gateway ensures Musawo reaches 100% of VHTs.
"""

from __future__ import annotations

import logging
import os

from app.config import settings
from app.i18n import t

logger = logging.getLogger("musawo.sms")

# ── Twilio Config (centralized in app.config) ──────────────────────────

TWILIO_ACCOUNT_SID = settings.twilio_account_sid
TWILIO_AUTH_TOKEN = settings.twilio_auth_token
TWILIO_PHONE_NUMBER = settings.twilio_phone_number  # e.g. +1234567890

_twilio_client = None

# ── USSD Session Locale Store ─────────────────────────────────────────
# Maps session_id -> locale code (e.g. "en", "lg", "nyn", "sw")
_ussd_session_locales: dict[str, str] = {}

LOCALE_MAP = {
    "1": "en",
    "2": "lg",
    "3": "nyn",
    "4": "sw",
}


def _get_twilio_client():
    global _twilio_client
    if _twilio_client is None:
        from twilio.rest import Client
        _twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return _twilio_client


# ── USSD Language Selection Menu ──────────────────────────────────────

USSD_LANGUAGE_MENU = (
    "CON Select Language / Londa Olulimi:\n\n"
    "1. English\n"
    "2. Luganda\n"
    "3. Runyankole\n"
    "4. Swahili"
)


# ── USSD Menu Builder (localized) ────────────────────────────────────

def _build_main_menu(locale: str) -> str:
    """Build the main USSD menu in the user's selected language."""
    return (
        f"CON {t('ussd_welcome', locale)}\n\n"
        f"1. {t('ussd_vht', locale)}\n"
        f"2. {t('ussd_maternal', locale)}\n"
        f"3. {t('ussd_emergency', locale)}\n"
        f"4. {t('ussd_nearest_clinic', locale)}"
    )


def _build_ussd_menu(locale: str) -> dict[str, str]:
    """Build the full USSD menu tree for a given locale.

    Sub-menus (clinical content) remain in English as they contain
    drug dosages and medical protocols that must not be mistranslated.
    Top-level navigation is localized.
    """
    return {
        "main": _build_main_menu(locale),
        "1": (
            f"CON {t('ussd_vht', locale)}:\n"
            "1. Child has fever\n"
            "2. Child has cough/fast breathing\n"
            "3. Child has diarrhoea\n"
            "4. Child has danger signs\n"
            "0. Back"
        ),
        "1*1": (
            "END FEVER in child:\n"
            "1. Do RDT test\n"
            "2. If RDT+: Give ACT\n"
            "   <12mo: 1 tab 2x/day 3days\n"
            "   >12mo: 2 tabs 2x/day 3days\n"
            "3. If RDT-: Do NOT give ACT\n"
            "4. If fever >3 days: REFER\n"
            "Call 0800100263 for help"
        ),
        "1*2": (
            "END COUGH/FAST BREATHING:\n"
            "Count breaths for 1 FULL min\n"
            "Fast: 2-11mo >=50/min\n"
            "      12-59mo >=40/min\n"
            "If fast breathing:\n"
            "  Give Amoxicillin 5 days\n"
            "If chest indrawing:\n"
            "  REFER NOW - severe\n"
            "Call 0800100263"
        ),
        "1*3": (
            "END DIARRHOEA:\n"
            "1. Give ORS: mix 1 packet\n"
            "   in 1 litre clean water\n"
            "2. Give Zinc daily 10 days\n"
            "   <6mo: 10mg, >6mo: 20mg\n"
            "3. Continue breastfeeding\n"
            "4. If blood in stool: REFER\n"
            "5. If severe dehydration: REFER\n"
            "Call 0800100263"
        ),
        "1*4": (
            "END DANGER SIGNS - REFER NOW:\n"
            "- Cannot drink/breastfeed\n"
            "- Vomits everything\n"
            "- Convulsions/fits\n"
            "- Very sleepy/unconscious\n"
            "- Chest indrawing\n\n"
            "Give pre-referral treatment\n"
            "Write referral note\n"
            "Call facility: 0800100263"
        ),
        "2": (
            f"CON {t('ussd_maternal', locale)}:\n"
            "1. Pregnancy danger signs\n"
            "2. Breastfeeding help\n"
            "3. Newborn danger signs\n"
            "4. Family planning\n"
            "0. Back"
        ),
        "2*1": (
            "END PREGNANCY DANGER SIGNS:\n"
            "Go to facility NOW if:\n"
            "- Vaginal bleeding\n"
            "- Severe headache\n"
            "- Blurred vision\n"
            "- Convulsions/fits\n"
            "- High fever\n"
            "- Baby not moving\n"
            "- Water breaking early\n"
            "Call 0800100263 NOW"
        ),
        "2*2": (
            "END BREASTFEEDING:\n"
            "- Start within 1 hour of birth\n"
            "- Give ONLY breast milk\n"
            "  for first 6 months\n"
            "- Feed 8+ times per day\n"
            "- First yellow milk (colostrum)\n"
            "  is baby's first vaccine\n"
            "- Do NOT give water/formula\n"
            "Call 0800100263 for help"
        ),
        "2*3": (
            "END NEWBORN DANGER SIGNS:\n"
            "Take baby to facility if:\n"
            "- Not feeding/sucking\n"
            "- Convulsions\n"
            "- Fast breathing >60/min\n"
            "- Fever or feels cold\n"
            "- Yellow skin (jaundice)\n"
            "- Cord: red/pus/smell\n"
            "Call 0800100263 NOW"
        ),
        "2*4": (
            "END FAMILY PLANNING:\n"
            "Wait 2 years between births\n"
            "Options (all free at HC):\n"
            "- Implant (3-5 years)\n"
            "- Injectable (3 months)\n"
            "- IUD (5-12 years)\n"
            "- Condoms (also prevent STIs)\n"
            "- Pills\n"
            "Visit your health facility"
        ),
        "3": (
            f"END {t('ussd_emergency', locale).upper()}:\n"
            "Health Hotline: 0800100263\n"
            "Ambulance: 0800911911\n"
            "Poison Centre: +256414270975\n\n"
            "These are toll-free 24/7"
        ),
        "4": (
            f"END {t('ussd_nearest_clinic', locale).upper()}:\n"
            "Visit your nearest HC:\n"
            "- HC II: basic outpatient\n"
            "- HC III: maternity + lab\n"
            "- HC IV: surgery + blood\n"
            "- Hospital: specialists\n\n"
            "Ask VHT for directions\n"
            "or call 0800100263"
        ),
    }


# ── USSD Handler ───────────────────────────────────────────────────────

def handle_ussd_callback(
    session_id: str,
    phone_number: str,
    text: str,
    service_code: str,
) -> str:
    """Process USSD callback. Returns CON (continue) or END (terminate).

    The first menu is always the language selection. Once a language is
    chosen, it is stored for the session and subsequent menus are shown
    in that locale.
    """
    logger.info("USSD: session=%s phone=%s text=%s", session_id, phone_number, text)

    # No input yet — show language selection menu
    if text == "":
        return USSD_LANGUAGE_MENU

    parts = text.split("*")

    # First selection is always the language choice
    lang_choice = parts[0]
    locale = LOCALE_MAP.get(lang_choice, "en")
    _ussd_session_locales[session_id] = locale

    # After language selection, the remaining input navigates the health menu
    remaining_parts = parts[1:]
    menu_key = "*".join(remaining_parts)

    # Build the localized menu tree
    menu = _build_ussd_menu(locale)

    # If only language was selected (no further navigation), show main menu
    if not remaining_parts:
        return menu["main"]

    # Look up the menu entry
    response = menu.get(menu_key)
    if response:
        return response

    # Handle "0" (Back) navigation
    if menu_key.endswith("*0"):
        parent = "*".join(menu_key.split("*")[:-2])
        return menu.get(parent, menu["main"])

    # Fallback to main menu
    return menu["main"]


# ── SMS via Twilio ─────────────────────────────────────────────────────

def truncate_for_sms(text: str, max_chars: int = 1600) -> list[str]:
    """Split text into SMS segments. Twilio supports long SMS (up to 1600 chars)
    which get auto-concatenated on the receiver's phone."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    words = text.split()
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars - 10:
            current += (" " if current else "") + word
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)

    total = len(chunks)
    return [f"{chunk} ({i+1}/{total})" for i, chunk in enumerate(chunks)]


async def send_sms(phone: str, message: str) -> dict:
    """Send SMS via Twilio REST API.

    Args:
        phone: Recipient phone in E.164 format (e.g. +256701234567)
        message: Message body

    Returns:
        dict with sid, status, error (if any)
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured")
        return {"sid": None, "status": "failed", "error": "Twilio not configured"}

    try:
        client = _get_twilio_client()
        chunks = truncate_for_sms(message)
        results = []

        for chunk in chunks:
            msg = client.messages.create(
                body=chunk,
                from_=TWILIO_PHONE_NUMBER,
                to=phone,
            )
            results.append({"sid": msg.sid, "status": msg.status})
            logger.info("SMS sent: sid=%s to=%s status=%s", msg.sid, phone, msg.status)

        return {
            "sid": results[-1]["sid"] if results else None,
            "status": "sent",
            "segments": len(results),
        }

    except ImportError:
        logger.error("twilio package not installed — run: pip install twilio")
        return {"sid": None, "status": "failed", "error": "twilio package not installed"}
    except Exception as e:
        logger.error("Twilio SMS failed: %s", e)
        return {"sid": None, "status": "failed", "error": str(e)}


async def handle_incoming_sms(from_number: str, body: str, locale: str = "en") -> str:
    """Process an incoming SMS and return a health guidance response.

    This is called from the Twilio webhook when a user texts the Musawo number.
    Uses the triage agent for VHT queries, or returns quick-reference guidance.

    Args:
        from_number: Sender phone number in E.164 format
        body: SMS message body
        locale: Language code for the response (default "en")
    """
    logger.info("Incoming SMS from %s: %s", from_number, body[:100])

    body_lower = body.strip().lower()

    # Quick keyword responses (no LLM needed — instant)
    if body_lower in ("help", "menu", "hi", "hello"):
        return (
            "Welcome to Musawo AI Health Navigator!\n\n"
            "Text your health question, e.g.:\n"
            "- 'child fever' for malaria guidance\n"
            "- 'pregnant bleeding' for danger signs\n"
            "- 'clinic' for nearest facility\n"
            "- 'emergency' for hotline numbers\n\n"
            f"{t('sms_disclaimer', locale)}"
        )

    if body_lower in ("emergency", "sos", "help now"):
        return (
            "EMERGENCY CONTACTS:\n"
            "Health Hotline: 0800 100 263 (toll-free)\n"
            "Ambulance: 0800 911 911\n"
            "Poison Centre: +256-414-270-975\n\n"
            "Go to nearest health facility immediately."
        )

    if body_lower in ("clinic", "hospital", "facility", "nearest"):
        return (
            "NEAREST HEALTH FACILITIES:\n"
            "- HC II: basic outpatient care\n"
            "- HC III: maternity + laboratory\n"
            "- HC IV: surgery + blood bank\n"
            "- Hospital: specialist services\n\n"
            "Ask your VHT or call 0800 100 263 for directions."
        )

    # Danger sign detection (hard-coded, no LLM)
    danger_keywords = [
        "convulsion", "fits", "unconscious", "not breathing",
        "cannot drink", "cannot breastfeed", "severe bleeding",
        "chest indrawing",
    ]
    if any(kw in body_lower for kw in danger_keywords):
        return (
            "DANGER SIGN DETECTED!\n"
            "REFER TO HEALTH FACILITY IMMEDIATELY.\n\n"
            "While waiting:\n"
            "- Keep patient on their side\n"
            "- Do NOT put anything in mouth\n"
            "- Give pre-referral treatment if trained\n\n"
            "Call NOW: 0800 100 263"
        )

    # Default: provide general guidance with disclaimer
    return (
        f"Thank you for your question about: {body[:80]}\n\n"
        "For detailed guidance, visit musawo.health or use the Musawo app.\n\n"
        "If symptoms are severe, go to the nearest health facility immediately.\n\n"
        f"{t('sms_disclaimer', locale)}"
    )
