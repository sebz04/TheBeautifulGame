"""Deterministic fallback texts: 4 personas × 5 languages, from the verified claims alone.

When an agent's text can't be verified, the fan sees one of these instead, so the screen is
never blank and never wrong (Constitution II). Every number comes from a claim, written the
way the language writes numbers; labels carry no digits or number words, so the number
check reads only the claims' values. Arabic texts are marked ``dir="rtl"``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from matchmind.schemas import Claim, Insight, Lang, Persona, PersonalizedText, Variant

WORD_LIMITS: dict[Persona, int] = {"analyst": 90, "casual": 45, "club_fan": 60, "player_focus": 60}
JARGON = ("xT", "PPDA", "field tilt", "pitch control")
_JARGON_RE = [
    (term, re.compile(rf"\b{re.escape(term)}\b", 0 if term in ("xT", "PPDA") else re.IGNORECASE))
    for term in JARGON
]
_SCOPE = re.compile(r"/(?:team|player):(?P<id>.+)$")
_ARABIC = str.maketrans("0123456789.", "٠١٢٣٤٥٦٧٨٩٫")
MAX_CLAIMS: dict[Persona, int] = {"analyst": 5, "casual": 2, "club_fan": 3, "player_focus": 3}

# Plain labels per language (no digits, no number words, no jargon).
LABELS: dict[str, dict[Lang, str]] = {
    "goals": {"en": "goals", "es": "goles", "pt": "gols", "fr": "buts", "ar": "الأهداف"},
    "goal": {"en": "goal", "es": "gol", "pt": "gol", "fr": "but", "ar": "هدف"},
    "assists": {"en": "assists", "es": "asistencias", "pt": "assistências",
                "fr": "passes décisives", "ar": "التمريرات الحاسمة"},
    "shots": {"en": "shots", "es": "remates", "pt": "finalizações", "fr": "tirs",
              "ar": "التسديدات"},
    "shots_on_target": {"en": "shots on target", "es": "remates al arco", "pt": "chutes no gol",
                        "fr": "tirs cadrés", "ar": "التسديدات على المرمى"},
    "xg": {"en": "chance quality (expected goals)",
           "es": "calidad de ocasiones (goles esperados)",
           "pt": "qualidade das chances (gols esperados)",
           "fr": "qualité des occasions (buts attendus)", "ar": "جودة الفرص (الأهداف المتوقعة)"},
    "passes": {"en": "passes", "es": "pases", "pt": "passes", "fr": "passes", "ar": "التمريرات"},
    "completed": {"en": "completed passes", "es": "pases completados",
                  "pt": "passes certos", "fr": "passes réussies", "ar": "التمريرات الناجحة"},
    "pass_completion": {"en": "passes completed", "es": "pases completados",
                        "pt": "passes certos", "fr": "passes réussies", "ar": "دقة التمرير"},
    "pass_accuracy": {"en": "passing accuracy", "es": "precisión de pase",
                      "pt": "precisão de passe", "fr": "précision des passes", "ar": "دقة التمرير"},
    "possession": {"en": "possession", "es": "posesión", "pt": "posse de bola",
                   "fr": "possession", "ar": "الاستحواذ"},
    "ppda": {"en": "pressing (passes allowed per defensive action)",
             "es": "presión (pases permitidos por acción defensiva)",
             "pt": "pressão (passes permitidos por ação defensiva)",
             "fr": "pressing (passes concédées par action défensive)",
             "ar": "الضغط (التمريرات المسموح بها لكل إجراء دفاعي)"},
    "ppda_10min": {"en": "recent pressing (passes allowed per defensive action)",
                   "es": "presión reciente (pases permitidos por acción defensiva)",
                   "pt": "pressão recente (passes permitidos por ação defensiva)",
                   "fr": "pressing récent (passes concédées par action défensive)",
                   "ar": "الضغط مؤخراً (التمريرات المسموح بها لكل إجراء دفاعي)"},
    "field_tilt_10min": {"en": "share of recent attacking-third passes",
                         "es": "parte de los pases recientes en el último tercio",
                         "pt": "parte dos passes recentes no terço final",
                         "fr": "part des passes récentes dans le dernier tiers",
                         "ar": "حصة التمريرات الأخيرة في الثلث الهجومي"},
    "momentum": {"en": "attacking momentum", "es": "impulso ofensivo", "pt": "embalo ofensivo",
                 "fr": "dynamique offensive", "ar": "الزخم الهجومي"},
    "territory": {"en": "share of the pitch controlled", "es": "parte del campo controlada",
                  "pt": "parte do campo controlada", "fr": "part du terrain contrôlée",
                  "ar": "حصة الملعب المسيطر عليها"},
    "corners": {"en": "corners", "es": "córners", "pt": "escanteios", "fr": "corners",
                "ar": "الركنيات"},
    "fouls": {"en": "fouls", "es": "faltas", "pt": "faltas", "fr": "fautes", "ar": "الأخطاء"},
    "offsides": {"en": "offsides", "es": "fueras de juego", "pt": "impedimentos",
                 "fr": "hors-jeu", "ar": "التسللات"},
    "yellow": {"en": "yellow cards", "es": "tarjetas amarillas", "pt": "cartões amarelos",
               "fr": "cartons jaunes", "ar": "البطاقات الصفراء"},
    "red": {"en": "red cards", "es": "tarjetas rojas", "pt": "cartões vermelhos",
            "fr": "cartons rouges", "ar": "البطاقات الحمراء"},
    "card": {"en": "card", "es": "tarjeta", "pt": "cartão", "fr": "carton", "ar": "بطاقة"},
    "players": {"en": "players on the pitch", "es": "jugadores en el campo",
                "pt": "jogadores em campo", "fr": "joueurs sur le terrain",
                "ar": "اللاعبون في الملعب"},
    "xt_added": {"en": "threat created", "es": "peligro generado", "pt": "perigo criado",
                 "fr": "danger créé", "ar": "الخطورة المصنوعة"},
    "key_passes": {"en": "key passes", "es": "pases clave", "pt": "passes decisivos",
                   "fr": "passes clés", "ar": "التمريرات المفتاحية"},
    "tackles": {"en": "tackles", "es": "entradas", "pt": "desarmes", "fr": "tacles",
                "ar": "الافتكاكات"},
    "interceptions": {"en": "interceptions", "es": "intercepciones", "pt": "interceptações",
                      "fr": "interceptions", "ar": "الاعتراضات"},
    "dribbles": {"en": "dribbles", "es": "regates", "pt": "dribles", "fr": "dribbles",
                 "ar": "المراوغات"},
    "counterfactual_gain": {"en": "extra value of the better option",
                            "es": "valor extra de la mejor opción",
                            "pt": "valor extra da melhor opção",
                            "fr": "valeur en plus de la meilleure option",
                            "ar": "القيمة الإضافية للخيار الأفضل"},
}  # fmt: skip
# Analysts get the standard name too.
ABBR = {"ppda": "PPDA", "ppda_10min": "PPDA", "field_tilt_10min": "field tilt", "xg": "xG",
        "xt_added": "xT", "counterfactual_gain": "xT"}  # fmt: skip

HEADLINES: dict[Persona, dict[Lang, str]] = {
    "analyst": {"en": "Analysis: {subject}", "es": "Análisis: {subject}",
                "pt": "Análise: {subject}", "fr": "Analyse : {subject}", "ar": "تحليل: {subject}"},
    "casual": {"en": "What just happened: {subject}", "es": "Qué acaba de pasar: {subject}",
               "pt": "O que aconteceu: {subject}", "fr": "Ce qui vient de se passer : {subject}",
               "ar": "ماذا حدث: {subject}"},
    "club_fan": {"en": "For {club} fans", "es": "Para la hinchada de {club}",
                 "pt": "Para a torcida do {club}", "fr": "Pour les supporters de {club}",
                 "ar": "لجماهير {club}"},
    "player_focus": {"en": "{player} in focus", "es": "{player} en foco",
                     "pt": "{player} em foco", "fr": "{player} à la loupe",
                     "ar": "{player} تحت المجهر"},
}  # fmt: skip
INTROS: dict[Persona, dict[Lang, str]] = {
    "analyst": {"en": "The numbers behind this moment.", "es": "Los números de esta jugada.",
                "pt": "Os números deste lance.", "fr": "Les chiffres de ce moment.",
                "ar": "أرقام هذه اللحظة."},
    "casual": {"en": "In short:", "es": "En resumen:", "pt": "Resumindo:", "fr": "En bref :",
               "ar": "باختصار:"},
    "club_fan": {"en": "How it looks for {club}.", "es": "Así se ve para {club}.",
                 "pt": "Como fica para o {club}.", "fr": "Ce que ça donne pour {club}.",
                 "ar": "كيف يبدو الأمر لـ {club}."},
    "player_focus": {"en": "What {player} has done.", "es": "Lo que ha hecho {player}.",
                     "pt": "O que {player} fez.", "fr": "Ce qu'a fait {player}.",
                     "ar": "ما قدّمه {player}."},
}  # fmt: skip
THE_MATCH: dict[Lang, str] = {"en": "the match", "es": "el partido", "pt": "a partida",
                              "fr": "le match", "ar": "المباراة"}  # fmt: skip
# When no team or player is named, "What just happened: the match" reads oddly.
MATCH_HEADLINES: dict[Persona, dict[Lang, str]] = {
    "analyst": {"en": "Match analysis", "es": "Análisis del partido", "pt": "Análise da partida",
                "fr": "Analyse du match", "ar": "تحليل المباراة"},
    "casual": {"en": "What just happened", "es": "Qué acaba de pasar", "pt": "O que aconteceu",
               "fr": "Ce qui vient de se passer", "ar": "ماذا حدث"},
}  # fmt: skip
_FR_VOWEL = re.compile(r"\bde ([AEIOUYHÀÂÉÈÊËÎÏÔÛÜaeiouyhàâéèêëîïôûü])")
NO_NUMBERS: dict[Lang, str] = {
    "en": "The full breakdown is on its way.", "es": "El análisis completo llegará pronto.",
    "pt": "A análise completa chega em breve.", "fr": "L'analyse complète arrive bientôt.",
    "ar": "التحليل الكامل في الطريق.",
}  # fmt: skip


def word_count(text: str) -> int:
    return len(text.split())


def jargon_in(text: str) -> list[str]:
    """Jargon terms in ``text`` (``xT`` and ``PPDA`` as whole words, case-sensitive)."""
    return [term for term, rx in _JARGON_RE if rx.search(text)]


def _about(claim: Claim) -> str | None:
    m = _SCOPE.search(claim.ref)
    return m["id"] if m else None


def format_value(claim: Claim, lang: Lang, *, with_unit: bool = True) -> str:
    """The claim's value as ``lang`` writes it: decimal comma (es, pt, fr), Arabic digits."""
    v, unit = claim.value, claim.unit.strip()
    if unit == "%" and abs(v) <= 1.0:
        text, suffix = f"{v * 100:.1f}", "%"
    elif float(v).is_integer():
        text, suffix = str(int(v)), ""
    else:
        text = f"{v:.3f}" if abs(v) < 0.1 else f"{v:.2f}" if abs(v) < 1 else f"{v:.1f}"
        suffix = f" {unit}" if with_unit and unit and unit != "%" else ""
    if unit == "%" and abs(v) > 1.0:
        suffix = "%"
    if lang in ("es", "pt", "fr"):
        text = text.replace(".", ",")
    if lang == "ar":
        return text.translate(_ARABIC) + suffix.replace("%", "٪")
    return text + (" %" if lang == "fr" and suffix == "%" else suffix)


def _label(claim: Claim, persona: Persona, lang: Lang) -> str | None:
    plain = LABELS.get(claim.metric, {}).get(lang)
    if persona == "analyst":
        abbr = ABBR.get(claim.metric)
        if plain is None:
            return claim.metric.replace("_", " ")
        if abbr and plain.endswith(")"):
            return f"{plain[:-1]}, {abbr})"
        return f"{plain} ({abbr})" if abbr else plain
    return plain


def _ordered(claims: list[Claim], variant: Variant) -> list[Claim]:
    focus = variant.club_id or variant.player_id
    return sorted(claims, key=lambda c: _about(c) != focus) if focus else list(claims)


def _subject(insight: Insight, names: Mapping[str, str], lang: Lang) -> str | None:
    scopes = [s for c in insight.claims if (s := _about(c))]
    players = [s for c in insight.claims if "/player:" in c.ref and (s := _about(c))]
    pick = players[0] if insight.level == "player" and players else scopes[0] if scopes else None
    return names.get(pick, pick) if pick else None


def _french(text: str) -> str:
    """French typography: "de" elides before a vowel ("d'Atlético"), and a colon takes a
    space before it ("Possession : 53,8 %")."""
    return re.sub(r"(?<=\S):", " :", _FR_VOWEL.sub(r"d'\1", text))


def render(
    insight: Insight, variant: Variant, lang: Lang, names: Mapping[str, str]
) -> PersonalizedText:
    """The fallback text for one persona and language, built from ``insight``'s claims."""
    persona = variant.persona
    club = names.get(variant.club_id or "", variant.club_id or "")
    player = names.get(variant.player_id or "", variant.player_id or "")
    subject = _subject(insight, names, lang)
    fill = {"subject": subject or THE_MATCH[lang], "club": club, "player": player}
    if subject is None and persona in MATCH_HEADLINES:
        headline = MATCH_HEADLINES[persona][lang]
    else:
        headline = HEADLINES[persona][lang].format(**fill)
    lines = []
    for c in _ordered(insight.claims, variant):
        label = _label(c, persona, lang)
        if label is None:
            continue
        about = names.get(_about(c) or "") if persona != "casual" else None
        value = format_value(c, lang, with_unit=persona == "analyst")
        comma = "،" if lang == "ar" else ","
        line = f"{about}{comma} {label}: {value}." if about else f"{label}: {value}."
        lines.append(line[0].upper() + line[1:])
        if len(lines) == MAX_CLAIMS[persona]:
            break
    body = " ".join([INTROS[persona][lang].format(**fill), *(lines or [NO_NUMBERS[lang]])])
    if lang == "fr":
        headline, body = _french(headline), _french(body)
    return PersonalizedText(
        insight_id=insight.insight_id, persona=persona, lang=lang, headline=headline,
        body=body, verified=True, club_id=variant.club_id, player_id=variant.player_id,
        dir="rtl" if lang == "ar" else "ltr", source="template",
    )  # fmt: skip
