"""Musawo AI — Centralized internationalization (i18n) string table.

All user-facing strings in English, Luganda, Runyankole, and Swahili.
Usage:  from app.i18n import t
        message = t("abstention", locale)
"""

from __future__ import annotations

_STRINGS: dict[str, dict[str, str]] = {
    # ── Guardrails & safety ──────────────────────────────────────────────
    "empty_input": {
        "en": "Please describe your health concern.",
        "lg": "Tusaba otegeeze ensonga y'obulamu bwo.",
        "nyn": "Turebereze obuhaise bw'amagara gawe.",
        "sw": "Tafadhali eleza wasiwasi wako wa afya.",
    },
    "input_too_long": {
        "en": "Your message is too long. Please shorten it and try again.",
        "lg": "Obubaka bwo buwanvu ennyo. Tubusaze okeeze.",
        "nyn": "Obubaka bwawe nibureingire. Bukupe ogaruke.",
        "sw": "Ujumbe wako ni mrefu sana. Tafadhali fupisha na ujaribu tena.",
    },
    "input_blocked": {
        "en": "I can only provide health guidance — I cannot prescribe, diagnose, or assist with harmful activities. Please consult a qualified health worker.",
        "lg": "Nsobola okukuwa obuyambi bw'obulamu kyokka — sisobola kulagira ddagala, okulambulula, oba okuyamba mu bikolwa ebyakabi. Tusaba ogendere omusawo akugu.",
        "nyn": "Ninabasa okukuha obuyambi bw'obuhaise obukuru — tindikubasa kukuhabiira eddagara, okurambulura, nari okuyamba omu bintu bibi. Gendaho omusawo omukugu.",
        "sw": "Naweza kutoa mwongozo wa afya tu — siwezi kuagiza dawa, kuchunguza, au kusaidia shughuli hatari. Tafadhali muone mtaalamu wa afya.",
    },
    "crisis_escalation": {
        "en": "If you or someone you know is in crisis, please call the Uganda Mental Health Hotline: **0800 100 263** (toll-free) or visit the nearest health facility immediately.",
        "lg": "Oba ggwe oba omuntu gw'omanyi ali mu kabi, yita ku simu eno: **0800 100 263** (ya bwereere) oba genda mu ddwaliro erisinga okuba okumpi amangu ddala.",
        "nyn": "Nooba iwe nari omuntu ogu omanyire ali omu buzibu, koroha **0800 100 263** (ya bure) nari ogendere omu irwariro erisinga okuba hakuuhi hati nyowe.",
        "sw": "Ikiwa wewe au mtu unayemjua yupo katika hali ya hatari, tafadhali piga simu **0800 100 263** (bila malipo) au nenda hospitali ya karibu mara moja.",
    },

    # ── Abstention & escalation ──────────────────────────────────────────
    "abstention": {
        "en": "I don't have enough information in the health guidelines to answer this question reliably. Please visit your nearest health facility or call the health hotline: **0800 100 263** (toll-free).",
        "lg": "Sirina bukimu bumala mu biragiro by'obulamu okuddamu ekibuuzo kino. Genda mu ddwaliro erisinga okuba okumpi oba yita ku simu **0800 100 263** (ya bwereere).",
        "nyn": "Tinyine buhangwa buhikire omu mateeka g'obuhaise okusubiza ekibuuzo kino. Genda omu irwariro erisinga okuba hakuuhi nari koroha **0800 100 263** (ya bure).",
        "sw": "Sina taarifa za kutosha katika miongozo ya afya kujibu swali hili kwa uhakika. Tafadhali nenda hospitali ya karibu au piga simu **0800 100 263** (bila malipo).",
    },
    "escalation_message": {
        "en": "Please visit the nearest health facility or call **0800 100 263** (toll-free).",
        "lg": "Tusaba ogendere mu ddwaliro erisinga okuba okumpi oba oyite ku simu **0800 100 263** (ya bwereere).",
        "nyn": "Genda omu irwariro erisinga okuba hakuuhi nari koroha **0800 100 263** (ya bure).",
        "sw": "Tafadhali nenda hospitali ya karibu au piga simu **0800 100 263** (bila malipo).",
    },
    "low_confidence": {
        "en": "Low confidence — recommend facility visit.",
        "lg": "Obukakamu butono — tugamba ogendere mu ddwaliro.",
        "nyn": "Obukakamu butono — tukugambirira ogendere omu irwariro.",
        "sw": "Uhakika mdogo — tunapendekeza kutembelea hospitali.",
    },

    # ── Disclaimers ──────────────────────────────────────────────────────
    "disclaimer": {
        "en": "This is health guidance only — not a medical diagnosis. If symptoms worsen or you are unsure, visit the nearest health facility or call the toll-free health hotline: **0800 100 263**.",
        "lg": "Buno bubaka bw'obuyambi bw'obulamu kyokka — si bulamu bwa musawo. Obubonero bwe bweyongera oba tokakaanya, genda mu ddwaliro erisinga okuba okumpi oba yita ku simu **0800 100 263** (ya bwereere).",
        "nyn": "Obu ni buhangwa bw'obuhaise obukuru — tiburikuba obutibu. Obubonero nibweyongera nari otarimanya, genda omu irwariro erisinga okuba hakuuhi nari koroha **0800 100 263** (ya bure).",
        "sw": "Hii ni mwongozo wa afya tu — si uchunguzi wa daktari. Dalili zikizidi au huna uhakika, nenda hospitali ya karibu au piga simu **0800 100 263** (bila malipo).",
    },
    "grounding_warning": {
        "en": "Note: This response may not be fully supported by the official health guidelines. Please verify with a health worker.",
        "lg": "Kijjukire: Okuddamu kuno kuyinza obutabeera kukkakkanyiziddwa ddala mu biragiro by'obulamu. Tusaba okakase n'omusawo.",
        "nyn": "Kijukire: Okusubiza kuno kutirikubera kukakasibwe ddala omu mateeka g'obuhaise. Kakasa n'omusawo.",
        "sw": "Kumbuka: Jibu hili huenda halithibitishwi kikamilifu na miongozo rasmi ya afya. Tafadhali thibitisha na mtaalamu wa afya.",
    },

    # ── LLM fallback messages ────────────────────────────────────────────
    "llm_timeout": {
        "en": "I'm having trouble generating a response right now. Based on the guidelines, here's what may help:",
        "lg": "Nnina obuzibu okukuddamu kiseera kino. Okusinziira ku biragiro, bino by'oyinza okuyambibwa:",
        "nyn": "Nineine obuzibu okugusubiza obu bwire. Okurugirira ahamateeka, ebi nibye byakuyamba:",
        "sw": "Ninashida kutoa jibu kwa sasa. Kulingana na miongozo, hapa ndipo yanaweza kusaidia:",
    },
    "llm_error": {
        "en": "I'm temporarily unable to generate a response. Please try again, or call the health hotline: **0800 100 263**.",
        "lg": "Sisobola kukuddamu kiseera kino. Keeza nate, oba yita ku simu: **0800 100 263**.",
        "nyn": "Tindiikubasa okugusubiza obu bwire. Garuka ogeeze nate, nari koroha: **0800 100 263**.",
        "sw": "Siwezi kutoa jibu kwa sasa. Tafadhali jaribu tena, au piga simu: **0800 100 263**.",
    },
    "prompt_leakage": {
        "en": "I apologize, but I had trouble generating a proper response. Please rephrase your question.",
        "lg": "Nsonyiwa, nze nafuna obuzibu okukuddamu. Tusaba okyuse ekibuuzo kyo.",
        "nyn": "Nsonyiwe, ninabire obuzibu okugusubiza. Hindura ekibuuzo kyawe.",
        "sw": "Samahani, nilikuwa na shida kutoa jibu sahihi. Tafadhali uliza kwa njia nyingine.",
    },

    # ── Triage agent ─────────────────────────────────────────────────────
    "triage_ask_age": {
        "en": "How old is the child? (months or years)",
        "lg": "Omwana alina emyaka emeka? (emyezi oba emyaka)",
        "nyn": "Omwana aine emyaka engahe? (emyeezi nari emyaka)",
        "sw": "Mtoto ana umri gani? (miezi au miaka)",
    },
    "triage_ask_symptoms": {
        "en": "What symptoms does the child have? (fever, cough, diarrhoea, vomiting, etc.)",
        "lg": "Omwana alina bubonero ki? (omusujja, okufuuwa, ekiddukaano, okusesema, n'ebirala)",
        "nyn": "Omwana aine obubonero ki? (omushuija, okukora, okushaarira, okushuuha, n'ebindi)",
        "sw": "Mtoto ana dalili gani? (homa, kikohozi, kuharisha, kutapika, nk.)",
    },
    "triage_danger_detected": {
        "en": "**REFER NOW** — DANGER SIGNS DETECTED. Take the child to the nearest health facility IMMEDIATELY.",
        "lg": "**TUMYA AMANGU** — OBUBONERO BW'AKABI BUMANYIDDWA. Twala omwana mu ddwaliro erisinga okuba okumpi AMANGU DDALA.",
        "nyn": "**TUMYA HATI** — OBUBONERO BW'AKABI BUMANYIRWE. Twara omwana omu irwariro erisinga okuba hakuuhi HATI NYOWE.",
        "sw": "**PELEKA HARAKA** — DALILI ZA HATARI ZIMEGUNDULIWA. Peleka mtoto hospitali ya karibu MARA MOJA.",
    },
    "triage_refer_now": {
        "en": "REFER NOW — Go to the nearest health facility immediately.",
        "lg": "TUMYA AMANGU — Genda mu ddwaliro erisinga okuba okumpi amangu ddala.",
        "nyn": "TUMYA HATI — Genda omu irwariro erisinga okuba hakuuhi hati nyowe.",
        "sw": "PELEKA HARAKA — Nenda hospitali ya karibu mara moja.",
    },
    "triage_manage_home": {
        "en": "This can be managed at home. Follow these steps:",
        "lg": "Kino kisobola okulabirirwa awaka. Goberera emitendera gino:",
        "nyn": "Eki nikibasa okurabirirwa omuka. Kuratira ebitandiko ebi:",
        "sw": "Hii inaweza kushughulikiwa nyumbani. Fuata hatua hizi:",
    },
    "triage_monitor": {
        "en": "Monitor closely and return to the health facility if symptoms worsen.",
        "lg": "Mwesimire bulungi era oddemu mu ddwaliro obubonero bwe bweyongera.",
        "nyn": "Murinde naiwe ogarukire omu irwariro obubonero nibweyongera.",
        "sw": "Fuatilia kwa karibu na rudi hospitalini dalili zikizidi.",
    },
    "triage_fever_classify": {
        "en": "Possible Malaria — test with RDT if available.",
        "lg": "Malaria eyinzika — kebera ne RDT bwe giba eliyo.",
        "nyn": "Malaria eyinzire — kebera ne RDT neeba eriho.",
        "sw": "Malaria inayowezekana — pima na RDT kama inapatikana.",
    },
    "triage_pneumonia_classify": {
        "en": "Possible Pneumonia — count breathing rate for 1 full minute.",
        "lg": "Kafubo eyinzika — bala okussa kw'omwana okumale eddakiika 1 yonna.",
        "nyn": "Kafubo eyinzire — bara okuhuuha kw'omwana okumaire edakiika 1 yoona.",
        "sw": "Nimonia inayowezekana — hesabu kiwango cha kupumua kwa dakika 1 kamili.",
    },
    "triage_diarrhoea_classify": {
        "en": "Diarrhoea — assess dehydration level (skin pinch test, sunken eyes).",
        "lg": "Ekiddukaano — kebera amazzi ga mu mubiri (nyiga olususu, amaaso agayise mu kitwe).",
        "nyn": "Okushaarira — kebera amazi g'omu mubiri (nyiga okukoba, amaisho agayiire omu mutwe).",
        "sw": "Kuharisha — tathmini kiwango cha upungufu wa maji (pima ngozi, macho yaliyozama).",
    },
    "triage_followup": {
        "en": "Reassess within 24 hours if referred patient returns.",
        "lg": "Ddamu okukebera mu ssaawa 24 omulwadde bw'addayo.",
        "nyn": "Garuka okwebaza omu saawa 24 omurwaire nagaruka.",
        "sw": "Tathmini tena ndani ya masaa 24 mgonjwa akirudi.",
    },
    "triage_count_breathing": {
        "en": "Please **count the breathing rate for 1 FULL minute**. How many breaths?",
        "lg": "Tusaba **obale okussa kw'omwana okumale eddakiika 1 YONNA**. Assizze emirundi emeka?",
        "nyn": "Tukusaba **obare okuhuuha kw'omwana okumaire edakiika 1 YOONA**. Ahuuhire emirundi engahe?",
        "sw": "Tafadhali **hesabu kiwango cha kupumua kwa dakika 1 KAMILI**. Pumzi ngapi?",
    },
    "triage_check_danger": {
        "en": "First, let me check for danger signs. Does the child have any of these?",
        "lg": "Sooka, ka nkebere obubonero bw'akabi. Omwana alina kino kyonna?",
        "nyn": "Tandiika, reka nkebere obubonero bw'akabi. Omwana aine eki kyoona?",
        "sw": "Kwanza, acha niangalie dalili za hatari. Je, mtoto ana mojawapo ya hizi?",
    },

    # ── Frontend UI strings ──────────────────────────────────────────────
    "settings_title": {
        "en": "Settings", "lg": "Entegeka", "nyn": "Enteganyarizo", "sw": "Mipangilio",
    },
    "settings_connection": {
        "en": "Connection", "lg": "Okuyunga", "nyn": "Okuyunga", "sw": "Muunganisho",
    },
    "settings_online": {
        "en": "Online", "lg": "Ku yintaneeti", "nyn": "Ku intaneti", "sw": "Mtandaoni",
    },
    "settings_offline": {
        "en": "Offline", "lg": "Toli ku yintaneeti", "nyn": "Toli ku intaneti", "sw": "Nje ya mtandao",
    },
    "settings_accessibility": {
        "en": "Accessibility", "lg": "Okuyingira mangu", "nyn": "Okuyingira mangu", "sw": "Ufikiaji",
    },
    "settings_tts": {
        "en": "Voice Output (TTS)", "lg": "Eddoboozi (TTS)", "nyn": "Edoboozi (TTS)", "sw": "Sauti (TTS)",
    },
    "settings_font_size": {
        "en": "Font Size", "lg": "Obunene bw'Ennukuta", "nyn": "Obunene bw'Ennukuta", "sw": "Ukubwa wa Herufi",
    },
    "settings_high_contrast": {
        "en": "High Contrast", "lg": "Okulagana kw'Elangi okw'Amaanyi", "nyn": "Okulagana kw'Erangi okw'Amaani", "sw": "Utofautishaji Mkubwa",
    },
    "settings_data": {
        "en": "Data", "lg": "Ebikukwatako", "nyn": "Ebikukwataho", "sw": "Data",
    },
    "settings_about": {
        "en": "About Musawo AI", "lg": "Ebikwata ku Musawo AI", "nyn": "Ebikwata aha Musawo AI", "sw": "Kuhusu Musawo AI",
    },
    "settings_clear_cache": {
        "en": "Clear offline cache", "lg": "Jjamu ebikukwatako", "nyn": "Siba ebikukwataho", "sw": "Futa kache",
    },
    "error_boundary_title": {
        "en": "Something went wrong", "lg": "Waliwo ekikyamu", "nyn": "Hariho ekikyamu", "sw": "Kuna kosa limetokea",
    },
    "error_boundary_message": {
        "en": "Musawo AI encountered an error. Please try again, or call **0800 100 263** for emergencies.",
        "lg": "Musawo AI afunye ekikyamu. Keeza nate, oba yita ku simu **0800 100 263** mu mbeera ez'amangu.",
        "nyn": "Musawo AI abonye ekikyamu. Garuka ogeeze nate, nari koroha **0800 100 263** omu mbeera ez'amaani.",
        "sw": "Musawo AI imepata kosa. Tafadhali jaribu tena, au piga simu **0800 100 263** kwa dharura.",
    },
    "voice_not_supported": {
        "en": "Voice input is not supported in this browser.",
        "lg": "Eddoboozi terikukozesebwa mu browser eno.",
        "nyn": "Edoboozi terikukozesebwa omu browser eno.",
        "sw": "Kuingiza kwa sauti hakutumiki katika kivinjari hiki.",
    },
    "voice_error": {
        "en": "Could not start voice input. Please try again.",
        "lg": "Tetusobodde kutandika eddoboozi. Keeza nate.",
        "nyn": "Tetubashize kutandika edoboozi. Garuka ogeeze nate.",
        "sw": "Haikuwezekana kuanza kuingiza kwa sauti. Tafadhali jaribu tena.",
    },
    "conversations": {
        "en": "Conversations", "lg": "Emboozi", "nyn": "Emboozi", "sw": "Mazungumzo",
    },
    "new_chat": {
        "en": "New Chat", "lg": "Emboozi Empya", "nyn": "Emboozi Empya", "sw": "Mazungumzo Mapya",
    },
    "search_conversations": {
        "en": "Search conversations...", "lg": "Noonya emboozi...", "nyn": "Noonya emboozi...", "sw": "Tafuta mazungumzo...",
    },
    "no_conversations": {
        "en": "No conversations yet", "lg": "Tewali mboozi n'emu", "nyn": "Tahariho mboozi n'emwe", "sw": "Hakuna mazungumzo bado",
    },

    # ── USSD / SMS ───────────────────────────────────────────────────────
    "ussd_welcome": {
        "en": "Welcome to Musawo AI\nCommunity Health Navigator",
        "lg": "Tukusanyukidde ku Musawo AI\nOmuyambi w'Obulamu bw'Ekitundu",
        "nyn": "Tukushemererwa aha Musawo AI\nOmuyambi w'Obuhaise bw'Ekicweka",
        "sw": "Karibu Musawo AI\nMwongozo wa Afya ya Jamii",
    },
    "ussd_vht": {
        "en": "VHT Triage (Child illness)",
        "lg": "Okulambula VHT (Obulwadde bw'omwana)",
        "nyn": "Okulambula VHT (Obulwaire bw'omwana)",
        "sw": "VHT Triage (Ugonjwa wa mtoto)",
    },
    "ussd_maternal": {
        "en": "Maternal Health",
        "lg": "Obulamu bw'Abakyala ab'Embuto",
        "nyn": "Obuhaise bw'Abakyara ab'Einda",
        "sw": "Afya ya Uzazi",
    },
    "ussd_emergency": {
        "en": "Emergency Contacts",
        "lg": "Essimu ez'Amangu",
        "nyn": "Esimu ez'Amaani",
        "sw": "Nambari za Dharura",
    },
    "ussd_nearest_clinic": {
        "en": "Nearest Clinic",
        "lg": "Eddwaliro Erisinga Okuba Okumpi",
        "nyn": "Irwariro Erisinga Okuba Hakuuhi",
        "sw": "Hospitali ya Karibu",
    },
    "sms_disclaimer": {
        "en": "This is guidance only, not diagnosis. Call 0800 100 263 for emergencies.",
        "lg": "Buno bubaka bw'obuyambi kyokka, si bwa musawo. Yita 0800 100 263 mu mbeera ez'amangu.",
        "nyn": "Obu ni buhangwa obukuru, tiburikuba obutibu. Koroha 0800 100 263 omu mbeera ez'amaani.",
        "sw": "Hii ni mwongozo tu, si uchunguzi. Piga 0800 100 263 kwa dharura.",
    },
}


def t(key: str, locale: str = "en") -> str:
    """Get a translated string. Falls back to English if translation missing."""
    entry = _STRINGS.get(key)
    if not entry:
        return key
    return entry.get(locale, entry.get("en", key))


def t_fmt(key: str, locale: str = "en", **kwargs: str) -> str:
    """Get a translated string with format substitutions."""
    return t(key, locale).format(**kwargs)
