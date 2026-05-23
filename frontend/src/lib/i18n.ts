/**
 * Lightweight i18n for Musawo AI frontend.
 * Mirrors the backend i18n approach (backend/app/i18n.py).
 *
 * Usage:
 *   import { t } from "@/lib/i18n";
 *   const label = t("settings_title", locale);
 */

export type TranslationKey =
  | "settings_title"
  | "settings_connection"
  | "settings_online"
  | "settings_offline"
  | "settings_accessibility"
  | "settings_tts"
  | "settings_font_size"
  | "settings_high_contrast"
  | "settings_data"
  | "settings_about"
  | "settings_clear_cache"
  | "settings_clear_chat"
  | "settings_messages"
  | "settings_conversations"
  | "settings_status"
  | "settings_about_description"
  | "settings_about_disclaimer"
  | "settings_about_emergency"
  | "error_boundary_title"
  | "error_boundary_message"
  | "error_boundary_retry"
  | "voice_not_supported"
  | "voice_error"
  | "voice_listening"
  | "voice_starting"
  | "voice_speak_now"
  | "voice_cancel"
  | "voice_send"
  | "conversations"
  | "new_chat"
  | "search_conversations"
  | "no_conversations"
  | "grounding_warning";

type Translations = Record<TranslationKey, Record<string, string>>;

const translations: Translations = {
  settings_title: {
    en: "Settings",
    lg: "Entegeka",
    nyn: "Eby'okuteekawo",
    sw: "Mipangilio",
  },
  settings_connection: {
    en: "Connection",
    lg: "Enyunzi",
    nyn: "Okuhunga",
    sw: "Muunganisho",
  },
  settings_online: {
    en: "Online",
    lg: "Ku mutimbagano",
    nyn: "Ahari intaneti",
    sw: "Mtandaoni",
  },
  settings_offline: {
    en: "Offline",
    lg: "Tewali mutimbagano",
    nyn: "Tarikuriho intaneti",
    sw: "Nje ya mtandao",
  },
  settings_accessibility: {
    en: "Accessibility",
    lg: "Okuyingira",
    nyn: "Okutunga",
    sw: "Ufikivu",
  },
  settings_tts: {
    en: "Voice Output (TTS)",
    lg: "Eddoboozi (TTS)",
    nyn: "Amajwi (TTS)",
    sw: "Sauti (TTS)",
  },
  settings_font_size: {
    en: "Font Size",
    lg: "Obunene bw'ennukuta",
    nyn: "Obunene bw'ebaruha",
    sw: "Ukubwa wa herufi",
  },
  settings_high_contrast: {
    en: "High Contrast",
    lg: "Enjawulo ey'amaanyi",
    nyn: "Enjawura nkuru",
    sw: "Utofautishaji mkubwa",
  },
  settings_data: {
    en: "Data",
    lg: "Ebikozesebwa",
    nyn: "Amakuru",
    sw: "Data",
  },
  settings_about: {
    en: "About Musawo AI",
    lg: "Ebikwata ku Musawo AI",
    nyn: "Ebikwatire aha Musawo AI",
    sw: "Kuhusu Musawo AI",
  },
  settings_clear_cache: {
    en: "Clear offline cache",
    lg: "Jjamu ebisiikirize",
    nyn: "Siiba ebyahurikire",
    sw: "Futa kache",
  },
  settings_clear_chat: {
    en: "Clear chat history",
    lg: "Jjamu emboozi",
    nyn: "Siiba ebikuganire",
    sw: "Futa historia ya mazungumzo",
  },
  settings_messages: {
    en: "Messages",
    lg: "Obubaka",
    nyn: "Amakuru",
    sw: "Ujumbe",
  },
  settings_conversations: {
    en: "Conversations",
    lg: "Emboozi",
    nyn: "Ebikuganire",
    sw: "Mazungumzo",
  },
  settings_status: {
    en: "Status",
    lg: "Embeera",
    nyn: "Embeera",
    sw: "Hali",
  },
  settings_about_description: {
    en: "Community Health Navigator for rural Uganda. Built with official Ministry of Health guidelines.",
    lg: "Omukulembeze w'Ebyobulamu mu byalo bya Uganda. Yazimbibwa n'amateeka ga Minisitule y'Ebyobulamu.",
    nyn: "Omukuratsi w'Ebyobuzima mu byaro bya Uganda. Yaazimbwe n'amateeka ga Minisiteri y'Ebyobuzima.",
    sw: "Kiongozi wa Afya ya Jamii kwa Uganda vijijini. Imejengwa kwa miongozo rasmi ya Wizara ya Afya.",
  },
  settings_about_disclaimer: {
    en: "This is health guidance only \u2014 not a medical diagnosis.",
    lg: "Buno bubuulirizi bw'ebyobulamu bukka \u2014 si kulamula ndwadde.",
    nyn: "Obu n'obuyambi bw'ebyobuzima bwonka \u2014 tari kuteekateeka obuhwere.",
    sw: "Hii ni mwongozo wa afya tu \u2014 si utambuzi wa matibabu.",
  },
  settings_about_emergency: {
    en: "Emergency:",
    lg: "Amangu:",
    nyn: "Obujurizi:",
    sw: "Dharura:",
  },
  error_boundary_title: {
    en: "Something went wrong",
    lg: "Waliwo ekikyamu",
    nyn: "Hariho ekibi kiriho",
    sw: "Kuna tatizo limetokea",
  },
  error_boundary_message: {
    en: "Musawo AI encountered an error. You can try again, or call the health hotline: 0800 100 263 for immediate help.",
    lg: "Musawo AI efunye ensobi. Osobola okugezaako nate, oba okubira essimu ku: 0800 100 263 okufuna obuyambi amangu.",
    nyn: "Musawo AI eizire aha kibi. Obaasa kugezaho nakindi, nari okubira esimu aha: 0800 100 263 okufuna obuyambi bwango.",
    sw: "Musawo AI imekutana na hitilafu. Unaweza kujaribu tena, au piga simu ya dharura: 0800 100 263 kwa msaada wa haraka.",
  },
  error_boundary_retry: {
    en: "Try Again",
    lg: "Gezaako nate",
    nyn: "Gezaho nakindi",
    sw: "Jaribu tena",
  },
  voice_not_supported: {
    en: "Voice input is not supported in this browser",
    lg: "Okufuna eddoboozi tekukolebwa mu browser eno",
    nyn: "Okuhingura amajwi tirikukozesebwa omu browser eno",
    sw: "Kuingiza kwa sauti hakutumiki katika kivinjari hiki",
  },
  voice_error: {
    en: "Could not start voice input",
    lg: "Tekyasobose kutandika ddoboozi",
    nyn: "Tikyasoboire kutandika amajwi",
    sw: "Haikuweza kuanza kuingiza sauti",
  },
  voice_listening: {
    en: "Listening...",
    lg: "Mpuliriza...",
    nyn: "Ndikuhurira...",
    sw: "Inasikiliza...",
  },
  voice_starting: {
    en: "Starting...",
    lg: "Ntandika...",
    nyn: "Ndikutandika...",
    sw: "Inaanza...",
  },
  voice_speak_now: {
    en: "Speak now...",
    lg: "Yogera kati...",
    nyn: "Gamura hati...",
    sw: "Sema sasa...",
  },
  voice_cancel: {
    en: "Cancel",
    lg: "Sazaamu",
    nyn: "Garuka",
    sw: "Ghairi",
  },
  voice_send: {
    en: "Send",
    lg: "Weereza",
    nyn: "Tuma",
    sw: "Tuma",
  },
  conversations: {
    en: "Conversations",
    lg: "Emboozi",
    nyn: "Ebikuganire",
    sw: "Mazungumzo",
  },
  new_chat: {
    en: "New Chat",
    lg: "Emboozi empya",
    nyn: "Ebyokugana ebishya",
    sw: "Mazungumzo mapya",
  },
  search_conversations: {
    en: "Search conversations...",
    lg: "Noonya emboozi...",
    nyn: "Shakura ebikuganire...",
    sw: "Tafuta mazungumzo...",
  },
  no_conversations: {
    en: "No conversations yet",
    lg: "Tewali mboozi n'emu",
    nyn: "Tihariho bikuganire na bimwe",
    sw: "Hakuna mazungumzo bado",
  },
  grounding_warning: {
    en: "This response may not be fully supported by official guidelines.",
    lg: "Okuddamu kuno kuyinza obutaba kuyizibwa n'amateeka agakugu.",
    nyn: "Okugaruka kuno kwabaasa kutatunga obujurizi bw'amateeka ag'obufuzi.",
    sw: "Jibu hili huenda halithibitishwi kikamilifu na miongozo rasmi.",
  },
};

/**
 * Translate a key to the given locale. Falls back to English.
 */
export function t(key: string, locale: string = "en"): string {
  const entry = translations[key as TranslationKey];
  if (!entry) return key;
  return entry[locale] || entry["en"] || key;
}
