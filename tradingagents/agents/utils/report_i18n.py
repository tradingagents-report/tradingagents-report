"""Localize structured-report headings and enum display values.

Analyst/researcher prose already follows ``output_language`` via
``get_language_instruction``. Structured agents fill typed schemas and then
go through Python ``render_*`` helpers; those helpers read the active config
here so report chrome (headings, debate speaker prefixes, enum display) matches
the selected article language.

Canonical English enum *wire* values stay on the Pydantic models; only the
rendered markdown is localized. Downstream parsers accept the chrome spellings
from every known locale pack (see :mod:`tradingagents.agents.utils.rating`).

Locale packs align with the frontend/CLI article-language list
(``OUTPUT_LANGUAGE_IDS``). Unknown / Custom languages fall back to English
chrome so we never invent half-translated headings.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

# Buckets that have a full label/value map. Order matches frontend dropdown.
REPORT_LOCALES: tuple[str, ...] = (
    "english",
    "chinese",
    "japanese",
    "korean",
    "hindi",
    "spanish",
    "portuguese",
    "french",
    "german",
    "arabic",
    "russian",
)

# Alias → locale. Keys are lowercased / space-stripped forms plus native names.
_LOCALE_ALIASES: dict[str, str] = {
    # English
    "english": "english",
    "en": "english",
    "en_us": "english",
    "en-us": "english",
    # Chinese
    "chinese": "chinese",
    "zh": "chinese",
    "zh_cn": "chinese",
    "zh-cn": "chinese",
    "zh_hans": "chinese",
    "zh-hans": "chinese",
    "中文": "chinese",
    "简体中文": "chinese",
    "汉语": "chinese",
    # Japanese
    "japanese": "japanese",
    "ja": "japanese",
    "ja_jp": "japanese",
    "ja-jp": "japanese",
    "日本語": "japanese",
    # Korean
    "korean": "korean",
    "ko": "korean",
    "ko_kr": "korean",
    "ko-kr": "korean",
    "한국어": "korean",
    # Hindi
    "hindi": "hindi",
    "hi": "hindi",
    "hi_in": "hindi",
    "hi-in": "hindi",
    "हिन्दी": "hindi",
    "हिंदी": "hindi",
    # Spanish
    "spanish": "spanish",
    "es": "spanish",
    "es_es": "spanish",
    "es-es": "spanish",
    "español": "spanish",
    "espanol": "spanish",
    # Portuguese
    "portuguese": "portuguese",
    "pt": "portuguese",
    "pt_br": "portuguese",
    "pt-br": "portuguese",
    "pt_pt": "portuguese",
    "pt-pt": "portuguese",
    "português": "portuguese",
    "portugues": "portuguese",
    # French
    "french": "french",
    "fr": "french",
    "fr_fr": "french",
    "fr-fr": "french",
    "français": "french",
    "francais": "french",
    # German
    "german": "german",
    "de": "german",
    "de_de": "german",
    "de-de": "german",
    "deutsch": "german",
    # Arabic
    "arabic": "arabic",
    "ar": "arabic",
    "ar_sa": "arabic",
    "ar-sa": "arabic",
    "العربية": "arabic",
    # Russian
    "russian": "russian",
    "ru": "russian",
    "ru_ru": "russian",
    "ru-ru": "russian",
    "русский": "russian",
}

_LABEL_KEYS: tuple[str, ...] = (
    "recommendation",
    "rationale",
    "strategic_actions",
    "action",
    "reasoning",
    "entry_price",
    "stop_loss",
    "position_sizing",
    "final_transaction_proposal",
    "market_analysis_recommendation",
    "sentiment_analysis_recommendation",
    "news_analysis_recommendation",
    "fundamentals_analysis_recommendation",
    "rating",
    "executive_summary",
    "investment_thesis",
    "price_target",
    "time_horizon",
    "overall_sentiment",
    "score",
    "confidence",
    "bull_analyst",
    "bear_analyst",
    "aggressive_analyst",
    "conservative_analyst",
    "neutral_analyst",
)

_LABELS: dict[str, dict[str, str]] = {
    "english": {
        "recommendation": "Recommendation",
        "rationale": "Rationale",
        "strategic_actions": "Strategic Actions",
        "action": "Action",
        "reasoning": "Reasoning",
        "entry_price": "Entry Price",
        "stop_loss": "Stop Loss",
        "position_sizing": "Position Sizing",
        "final_transaction_proposal": "TRANSACTION PROPOSAL",
        "market_analysis_recommendation": "Market Analysis Recommendation",
        "sentiment_analysis_recommendation": "Sentiment Analysis Recommendation",
        "news_analysis_recommendation": "News Analysis Recommendation",
        "fundamentals_analysis_recommendation": "Fundamentals Analysis Recommendation",
        "rating": "Rating",
        "executive_summary": "Executive Summary",
        "investment_thesis": "Investment Thesis",
        "price_target": "Price Target",
        "time_horizon": "Time Horizon",
        "overall_sentiment": "Overall Sentiment",
        "score": "Score",
        "confidence": "Confidence",
        "bull_analyst": "Bull Analyst",
        "bear_analyst": "Bear Analyst",
        "aggressive_analyst": "Aggressive Analyst",
        "conservative_analyst": "Conservative Analyst",
        "neutral_analyst": "Neutral Analyst",
    },
    "chinese": {
        "recommendation": "建议",
        "rationale": "研究逻辑",
        "strategic_actions": "执行计划",
        "action": "操作",
        "reasoning": "理由",
        "entry_price": "入场价",
        "stop_loss": "止损",
        "position_sizing": "仓位",
        "final_transaction_proposal": "交易执行建议",
        "market_analysis_recommendation": "市场分析建议",
        "sentiment_analysis_recommendation": "情绪分析建议",
        "news_analysis_recommendation": "新闻分析建议",
        "fundamentals_analysis_recommendation": "基本面分析建议",
        "rating": "评级",
        "executive_summary": "执行摘要",
        "investment_thesis": "投资论点",
        "price_target": "目标价",
        "time_horizon": "持有周期",
        "overall_sentiment": "整体情绪",
        "score": "得分",
        "confidence": "置信度",
        "bull_analyst": "多头分析师",
        "bear_analyst": "空头分析师",
        "aggressive_analyst": "激进分析师",
        "conservative_analyst": "保守分析师",
        "neutral_analyst": "中性分析师",
    },
    "japanese": {
        "recommendation": "推奨",
        "rationale": "根拠",
        "strategic_actions": "戦略アクション",
        "action": "アクション",
        "reasoning": "理由",
        "entry_price": "エントリー価格",
        "stop_loss": "損切り",
        "position_sizing": "ポジションサイズ",
        "final_transaction_proposal": "取引提案",
        "market_analysis_recommendation": "マーケット分析の推奨",
        "sentiment_analysis_recommendation": "センチメント分析の推奨",
        "news_analysis_recommendation": "ニュース分析の推奨",
        "fundamentals_analysis_recommendation": "ファンダメンタルズ分析の推奨",
        "rating": "レーティング",
        "executive_summary": "エグゼクティブサマリー",
        "investment_thesis": "投資テーゼ",
        "price_target": "目標株価",
        "time_horizon": "投資期間",
        "overall_sentiment": "総合センチメント",
        "score": "スコア",
        "confidence": "確信度",
        "bull_analyst": "強気アナリスト",
        "bear_analyst": "弱気アナリスト",
        "aggressive_analyst": "積極アナリスト",
        "conservative_analyst": "保守アナリスト",
        "neutral_analyst": "中立アナリスト",
    },
    "korean": {
        "recommendation": "권고",
        "rationale": "근거",
        "strategic_actions": "전략 조치",
        "action": "조치",
        "reasoning": "이유",
        "entry_price": "진입가",
        "stop_loss": "손절가",
        "position_sizing": "포지션 규모",
        "final_transaction_proposal": "거래 제안",
        "market_analysis_recommendation": "시장 분석 권고",
        "sentiment_analysis_recommendation": "심리 분석 권고",
        "news_analysis_recommendation": "뉴스 분석 권고",
        "fundamentals_analysis_recommendation": "펀더멘털 분석 권고",
        "rating": "등급",
        "executive_summary": "요약",
        "investment_thesis": "투자 논거",
        "price_target": "목표가",
        "time_horizon": "투자기간",
        "overall_sentiment": "전체 심리",
        "score": "점수",
        "confidence": "신뢰도",
        "bull_analyst": "강세 분석가",
        "bear_analyst": "약세 분석가",
        "aggressive_analyst": "공격적 분석가",
        "conservative_analyst": "보수적 분석가",
        "neutral_analyst": "중립 분석가",
    },
    "hindi": {
        "recommendation": "सिफारिश",
        "rationale": "तर्क",
        "strategic_actions": "रणनीतिक कदम",
        "action": "कार्रवाई",
        "reasoning": "कारण",
        "entry_price": "प्रवेश मूल्य",
        "stop_loss": "स्टॉप लॉस",
        "position_sizing": "पोजीशन आकार",
        "final_transaction_proposal": "लेनदेन प्रस्ताव",
        "market_analysis_recommendation": "बाजार विश्लेषण सिफारिश",
        "sentiment_analysis_recommendation": "सेंटीमेंट विश्लेषण सिफारिश",
        "news_analysis_recommendation": "समाचार विश्लेषण सिफारिश",
        "fundamentals_analysis_recommendation": "फंडामेंटल विश्लेषण सिफारिश",
        "rating": "रेटिंग",
        "executive_summary": "सारांश",
        "investment_thesis": "निवेश थीसिस",
        "price_target": "लक्ष्य मूल्य",
        "time_horizon": "समय क्षितिज",
        "overall_sentiment": "समग्र सेंटीमेंट",
        "score": "स्कोर",
        "confidence": "विश्वास",
        "bull_analyst": "बुल विश्लेषक",
        "bear_analyst": "बेयर विश्लेषक",
        "aggressive_analyst": "आक्रामक विश्लेषक",
        "conservative_analyst": "रूढ़िवादी विश्लेषक",
        "neutral_analyst": "तटस्थ विश्लेषक",
    },
    "spanish": {
        "recommendation": "Recomendación",
        "rationale": "Fundamento",
        "strategic_actions": "Acciones estratégicas",
        "action": "Acción",
        "reasoning": "Razonamiento",
        "entry_price": "Precio de entrada",
        "stop_loss": "Stop loss",
        "position_sizing": "Tamaño de posición",
        "final_transaction_proposal": "PROPUESTA DE TRANSACCIÓN",
        "market_analysis_recommendation": "Recomendación de análisis de mercado",
        "sentiment_analysis_recommendation": "Recomendación de análisis de sentimiento",
        "news_analysis_recommendation": "Recomendación de análisis de noticias",
        "fundamentals_analysis_recommendation": "Recomendación de análisis fundamental",
        "rating": "Calificación",
        "executive_summary": "Resumen ejecutivo",
        "investment_thesis": "Tesis de inversión",
        "price_target": "Precio objetivo",
        "time_horizon": "Horizonte temporal",
        "overall_sentiment": "Sentimiento general",
        "score": "Puntuación",
        "confidence": "Confianza",
        "bull_analyst": "Analista alcista",
        "bear_analyst": "Analista bajista",
        "aggressive_analyst": "Analista agresivo",
        "conservative_analyst": "Analista conservador",
        "neutral_analyst": "Analista neutral",
    },
    "portuguese": {
        "recommendation": "Recomendação",
        "rationale": "Fundamento",
        "strategic_actions": "Ações estratégicas",
        "action": "Ação",
        "reasoning": "Raciocínio",
        "entry_price": "Preço de entrada",
        "stop_loss": "Stop loss",
        "position_sizing": "Tamanho da posição",
        "final_transaction_proposal": "PROPOSTA DE TRANSAÇÃO",
        "market_analysis_recommendation": "Recomendação de análise de mercado",
        "sentiment_analysis_recommendation": "Recomendação de análise de sentimento",
        "news_analysis_recommendation": "Recomendação de análise de notícias",
        "fundamentals_analysis_recommendation": "Recomendação de análise fundamentalista",
        "rating": "Classificação",
        "executive_summary": "Resumo executivo",
        "investment_thesis": "Tese de investimento",
        "price_target": "Preço-alvo",
        "time_horizon": "Horizonte temporal",
        "overall_sentiment": "Sentimento geral",
        "score": "Pontuação",
        "confidence": "Confiança",
        "bull_analyst": "Analista de alta",
        "bear_analyst": "Analista de baixa",
        "aggressive_analyst": "Analista agressivo",
        "conservative_analyst": "Analista conservador",
        "neutral_analyst": "Analista neutro",
    },
    "french": {
        "recommendation": "Recommandation",
        "rationale": "Justification",
        "strategic_actions": "Actions stratégiques",
        "action": "Action",
        "reasoning": "Raisonnement",
        "entry_price": "Prix d'entrée",
        "stop_loss": "Stop loss",
        "position_sizing": "Taille de position",
        "final_transaction_proposal": "PROPOSITION DE TRANSACTION",
        "market_analysis_recommendation": "Recommandation d'analyse de marché",
        "sentiment_analysis_recommendation": "Recommandation d'analyse du sentiment",
        "news_analysis_recommendation": "Recommandation d'analyse des actualités",
        "fundamentals_analysis_recommendation": "Recommandation d'analyse fondamentale",
        "rating": "Notation",
        "executive_summary": "Résumé exécutif",
        "investment_thesis": "Thèse d'investissement",
        "price_target": "Cours cible",
        "time_horizon": "Horizon temporel",
        "overall_sentiment": "Sentiment global",
        "score": "Score",
        "confidence": "Confiance",
        "bull_analyst": "Analyste haussier",
        "bear_analyst": "Analyste baissier",
        "aggressive_analyst": "Analyste agressif",
        "conservative_analyst": "Analyste conservateur",
        "neutral_analyst": "Analyste neutre",
    },
    "german": {
        "recommendation": "Empfehlung",
        "rationale": "Begründung",
        "strategic_actions": "Strategische Maßnahmen",
        "action": "Aktion",
        "reasoning": "Begründung",
        "entry_price": "Einstiegspreis",
        "stop_loss": "Stop-Loss",
        "position_sizing": "Positionsgröße",
        "final_transaction_proposal": "TRANSAKTIONSVORSCHLAG",
        "market_analysis_recommendation": "Marktanalyse-Empfehlung",
        "sentiment_analysis_recommendation": "Sentimentanalyse-Empfehlung",
        "news_analysis_recommendation": "Nachrichtenanalyse-Empfehlung",
        "fundamentals_analysis_recommendation": "Fundamentalanalyse-Empfehlung",
        "rating": "Bewertung",
        "executive_summary": "Kurzfassung",
        "investment_thesis": "Investmentthese",
        "price_target": "Kursziel",
        "time_horizon": "Zeithorizont",
        "overall_sentiment": "Gesamtsentiment",
        "score": "Punktzahl",
        "confidence": "Konfidenz",
        "bull_analyst": "Bullischer Analyst",
        "bear_analyst": "Bärischer Analyst",
        "aggressive_analyst": "Aggressiver Analyst",
        "conservative_analyst": "Konservativer Analyst",
        "neutral_analyst": "Neutraler Analyst",
    },
    "arabic": {
        "recommendation": "التوصية",
        "rationale": "المبرر",
        "strategic_actions": "الإجراءات الاستراتيجية",
        "action": "الإجراء",
        "reasoning": "التسويغ",
        "entry_price": "سعر الدخول",
        "stop_loss": "وقف الخسارة",
        "position_sizing": "حجم المركز",
        "final_transaction_proposal": "اقتراح الصفقة",
        "market_analysis_recommendation": "توصية تحليل السوق",
        "sentiment_analysis_recommendation": "توصية تحليل المعنويات",
        "news_analysis_recommendation": "توصية تحليل الأخبار",
        "fundamentals_analysis_recommendation": "توصية التحليل الأساسي",
        "rating": "التصنيف",
        "executive_summary": "الملخص التنفيذي",
        "investment_thesis": "أطروحة الاستثمار",
        "price_target": "السعر المستهدف",
        "time_horizon": "الأفق الزمني",
        "overall_sentiment": "المعنويات العامة",
        "score": "الدرجة",
        "confidence": "الثقة",
        "bull_analyst": "المحلل الصاعد",
        "bear_analyst": "المحلل الهابط",
        "aggressive_analyst": "المحلل الجريء",
        "conservative_analyst": "المحلل المحافظ",
        "neutral_analyst": "المحلل المحايد",
    },
    "russian": {
        "recommendation": "Рекомендация",
        "rationale": "Обоснование",
        "strategic_actions": "Стратегические действия",
        "action": "Действие",
        "reasoning": "Аргументация",
        "entry_price": "Цена входа",
        "stop_loss": "Стоп-лосс",
        "position_sizing": "Размер позиции",
        "final_transaction_proposal": "ПРЕДЛОЖЕНИЕ ПО СДЕЛКЕ",
        "market_analysis_recommendation": "Рекомендация рыночного анализа",
        "sentiment_analysis_recommendation": "Рекомендация анализа настроений",
        "news_analysis_recommendation": "Рекомендация анализа новостей",
        "fundamentals_analysis_recommendation": "Рекомендация фундаментального анализа",
        "rating": "Рейтинг",
        "executive_summary": "Краткое резюме",
        "investment_thesis": "Инвестиционный тезис",
        "price_target": "Целевая цена",
        "time_horizon": "Временной горизонт",
        "overall_sentiment": "Общий сентимент",
        "score": "Оценка",
        "confidence": "Уверенность",
        "bull_analyst": "Бычий аналитик",
        "bear_analyst": "Медвежий аналитик",
        "aggressive_analyst": "Агрессивный аналитик",
        "conservative_analyst": "Консервативный аналитик",
        "neutral_analyst": "Нейтральный аналитик",
    },
}

# Display values for structured enums. Keys are the English canonical forms.
# English locale omits overrides (identity). Include both lower/Title confidence.
_VALUES: dict[str, dict[str, str]] = {
    "chinese": {
        "Buy": "买入",
        "Overweight": "增持",
        "Hold": "持有",
        "Underweight": "减持",
        "Sell": "卖出",
        "Bullish": "看涨",
        "Mildly Bullish": "偏多",
        "Neutral": "中性",
        "Mixed": "分化",
        "Mildly Bearish": "偏空",
        "Bearish": "看跌",
        "low": "低",
        "medium": "中",
        "high": "高",
        "Low": "低",
        "Medium": "中",
        "High": "高",
    },
    "japanese": {
        "Buy": "買い",
        "Overweight": "オーバーウェイト",
        "Hold": "ホールド",
        "Underweight": "アンダーウェイト",
        "Sell": "売り",
        "Bullish": "強気",
        "Mildly Bullish": "やや強気",
        "Neutral": "中立",
        "Mixed": "まちまち",
        "Mildly Bearish": "やや弱気",
        "Bearish": "弱気",
        "low": "低",
        "medium": "中",
        "high": "高",
        "Low": "低",
        "Medium": "中",
        "High": "高",
    },
    "korean": {
        "Buy": "매수",
        "Overweight": "비중확대",
        "Hold": "보유",
        "Underweight": "비중축소",
        "Sell": "매도",
        "Bullish": "강세",
        "Mildly Bullish": "약한 강세",
        "Neutral": "중립",
        "Mixed": "혼조",
        "Mildly Bearish": "약한 약세",
        "Bearish": "약세",
        "low": "낮음",
        "medium": "중간",
        "high": "높음",
        "Low": "낮음",
        "Medium": "중간",
        "High": "높음",
    },
    "hindi": {
        "Buy": "खरीदें",
        "Overweight": "ओवरवेट",
        "Hold": "होल्ड",
        "Underweight": "अंडरवेट",
        "Sell": "बेचें",
        "Bullish": "तेजी",
        "Mildly Bullish": "हल्की तेजी",
        "Neutral": "तटस्थ",
        "Mixed": "मिश्रित",
        "Mildly Bearish": "हल्की मंदी",
        "Bearish": "मंदी",
        "low": "कम",
        "medium": "मध्यम",
        "high": "उच्च",
        "Low": "कम",
        "Medium": "मध्यम",
        "High": "उच्च",
    },
    "spanish": {
        "Buy": "Comprar",
        "Overweight": "Sobreponderar",
        "Hold": "Mantener",
        "Underweight": "Infraponderar",
        "Sell": "Vender",
        "Bullish": "Alcista",
        "Mildly Bullish": "Ligeramente alcista",
        "Neutral": "Neutral",
        "Mixed": "Mixto",
        "Mildly Bearish": "Ligeramente bajista",
        "Bearish": "Bajista",
        "low": "baja",
        "medium": "media",
        "high": "alta",
        "Low": "Baja",
        "Medium": "Media",
        "High": "Alta",
    },
    "portuguese": {
        "Buy": "Comprar",
        "Overweight": "Overweight",
        "Hold": "Manter",
        "Underweight": "Underweight",
        "Sell": "Vender",
        "Bullish": "Alta",
        "Mildly Bullish": "Levemente altista",
        "Neutral": "Neutro",
        "Mixed": "Misto",
        "Mildly Bearish": "Levemente baixista",
        "Bearish": "Baixa",
        "low": "baixa",
        "medium": "média",
        "high": "alta",
        "Low": "Baixa",
        "Medium": "Média",
        "High": "Alta",
    },
    "french": {
        "Buy": "Acheter",
        "Overweight": "Surpondérer",
        "Hold": "Conserver",
        "Underweight": "Sous-pondérer",
        "Sell": "Vendre",
        "Bullish": "Haussier",
        "Mildly Bullish": "Légèrement haussier",
        "Neutral": "Neutre",
        "Mixed": "Mixte",
        "Mildly Bearish": "Légèrement baissier",
        "Bearish": "Baissier",
        "low": "faible",
        "medium": "moyenne",
        "high": "élevée",
        "Low": "Faible",
        "Medium": "Moyenne",
        "High": "Élevée",
    },
    "german": {
        "Buy": "Kaufen",
        "Overweight": "Übergewichten",
        "Hold": "Halten",
        "Underweight": "Untergewichten",
        "Sell": "Verkaufen",
        "Bullish": "Bullisch",
        "Mildly Bullish": "Leicht bullisch",
        "Neutral": "Neutral",
        "Mixed": "Gemischt",
        "Mildly Bearish": "Leicht bärisch",
        "Bearish": "Bärisch",
        "low": "niedrig",
        "medium": "mittel",
        "high": "hoch",
        "Low": "Niedrig",
        "Medium": "Mittel",
        "High": "Hoch",
    },
    "arabic": {
        "Buy": "شراء",
        "Overweight": "زيادة الوزن",
        "Hold": "احتفاظ",
        "Underweight": "خفض الوزن",
        "Sell": "بيع",
        "Bullish": "صاعد",
        "Mildly Bullish": "صاعد قليلاً",
        "Neutral": "محايد",
        "Mixed": "متباين",
        "Mildly Bearish": "هابط قليلاً",
        "Bearish": "هابط",
        "low": "منخفض",
        "medium": "متوسط",
        "high": "مرتفع",
        "Low": "منخفض",
        "Medium": "متوسط",
        "High": "مرتفع",
    },
    "russian": {
        "Buy": "Покупать",
        "Overweight": "Избыточный вес",
        "Hold": "Держать",
        "Underweight": "Недостаточный вес",
        "Sell": "Продавать",
        "Bullish": "Бычий",
        "Mildly Bullish": "Умеренно бычий",
        "Neutral": "Нейтральный",
        "Mixed": "Смешанный",
        "Mildly Bearish": "Умеренно медвежий",
        "Bearish": "Медвежий",
        "low": "низкая",
        "medium": "средняя",
        "high": "высокая",
        "Low": "Низкая",
        "Medium": "Средняя",
        "High": "Высокая",
    },
}

_DEBATE_ROLE_KEYS: frozenset[str] = frozenset({
    "bull_analyst",
    "bear_analyst",
    "aggressive_analyst",
    "conservative_analyst",
    "neutral_analyst",
})

_ANALYST_RECOMMENDATION_KEYS: dict[str, str] = {
    "market": "market_analysis_recommendation",
    "sentiment": "sentiment_analysis_recommendation",
    "news": "news_analysis_recommendation",
    "fundamentals": "fundamentals_analysis_recommendation",
}

_RATING_WIRE_VALUES: tuple[str, ...] = (
    "Buy",
    "Overweight",
    "Hold",
    "Underweight",
    "Sell",
)


def _assert_locale_packs_complete() -> None:
    """Dev-time sanity: every locale has the same label keys."""
    for locale in REPORT_LOCALES:
        labels = _LABELS.get(locale)
        if labels is None:
            raise RuntimeError(f"missing label pack for {locale!r}")
        missing = [key for key in _LABEL_KEYS if key not in labels]
        if missing:
            raise RuntimeError(f"locale {locale!r} missing labels: {missing}")


_assert_locale_packs_complete()


def normalize_report_language(language: str | None) -> str:
    """Return a report-chrome locale id, or ``english`` for unknown/custom."""
    if not language or not str(language).strip():
        return "english"

    raw = str(language).strip()
    key = raw.lower().replace(" ", "")
    compact = key.replace("-", "_")

    for candidate in (key, compact, raw, raw.lower()):
        locale = _LOCALE_ALIASES.get(candidate)
        if locale:
            return locale

    # Prefix heuristics for common BCP-47 tags.
    if key.startswith("zh") or "chinese" in key or "中文" in raw:
        return "chinese"
    if key.startswith("ja") or "japanese" in key or "日本" in raw:
        return "japanese"
    if key.startswith("ko") or "korean" in key or "한국" in raw:
        return "korean"
    if key.startswith("hi") or "hindi" in key or "हिंद" in raw or "हिन्द" in raw:
        return "hindi"
    if key.startswith("es") or "spanish" in key or "español" in key:
        return "spanish"
    if key.startswith("pt") or "portuguese" in key or "portugu" in key:
        return "portuguese"
    if key.startswith("fr") or "french" in key or "français" in key:
        return "french"
    if key.startswith("de") or "german" in key or "deutsch" in key:
        return "german"
    if key.startswith("ar") or "arabic" in key or "العرب" in raw:
        return "arabic"
    if key.startswith("ru") or "russian" in key or "русск" in raw.lower():
        return "russian"

    return "english"


def get_report_language() -> str:
    """Resolve the active ``output_language`` into a localization bucket."""
    from tradingagents.dataflows.config import get_config

    return normalize_report_language(get_config().get("output_language", "English"))


def report_labels(language: str | None = None) -> Mapping[str, str]:
    """Return the label map for ``language`` (or the active config language)."""
    lang = (
        normalize_report_language(language)
        if language is not None
        else get_report_language()
    )
    return _LABELS.get(lang) or _LABELS["english"]


def localize_report_value(value: str, language: str | None = None) -> str:
    """Translate a known structured enum/display value for the report locale."""
    lang = (
        normalize_report_language(language)
        if language is not None
        else get_report_language()
    )
    if lang == "english":
        return value
    return _VALUES.get(lang, {}).get(value, value)


def get_transaction_proposal_phrase(language: str | None = None) -> str:
    """Trader trailing-proposal phrase (also referenced in analyst prompts)."""
    return report_labels(language)["final_transaction_proposal"]


def get_analyst_recommendation_phrase(
    section: str,
    language: str | None = None,
) -> str:
    """Return the section-scoped recommendation label for an analyst report."""
    key = _ANALYST_RECOMMENDATION_KEYS.get(section)
    if key is None:
        raise ValueError(
            f"Unknown analyst section {section!r}; expected one of "
            f"{sorted(_ANALYST_RECOMMENDATION_KEYS)}"
        )
    return report_labels(language)[key]


def get_debate_role_label(role: str, language: str | None = None) -> str:
    """Return the localized speaker prefix for a debate / risk analyst turn."""
    if role not in _DEBATE_ROLE_KEYS:
        raise ValueError(
            f"Unknown debate role {role!r}; expected one of "
            f"{sorted(_DEBATE_ROLE_KEYS)}"
        )
    return report_labels(language)[role]


def format_debate_argument(
    role: str,
    content: str,
    language: str | None = None,
) -> str:
    """Prefix a debate turn with the localized speaker label."""
    return f"{get_debate_role_label(role, language)}: {content}"


def iter_label_spellings(*keys: str) -> Iterable[str]:
    """Yield unique label spellings across all locale packs for the given keys."""
    seen: set[str] = set()
    for key in keys:
        for labels in _LABELS.values():
            value = labels.get(key)
            if not value or value in seen:
                continue
            seen.add(value)
            yield value


def rating_value_aliases() -> dict[str, str]:
    """Map localized (and English) rating display tokens → canonical wire value."""
    aliases: dict[str, str] = {}
    for wire in _RATING_WIRE_VALUES:
        aliases[wire.lower()] = wire
        aliases[wire] = wire
        for locale_values in _VALUES.values():
            localized = locale_values.get(wire)
            if not localized:
                continue
            aliases[localized] = wire
            aliases[localized.lower()] = wire
    return aliases


_CONVICTION_WIRE_VALUES: tuple[str, ...] = ("low", "medium", "high")
# Common LLM spellings that are not the locale-pack display token.
_CONVICTION_EXTRA_ALIASES: dict[str, str] = {
    "中等": "medium",
    "中等确信度": "medium",
    "较低": "low",
    "较高": "high",
}


def conviction_value_aliases() -> dict[str, str]:
    """Map localized conviction words → canonical low/medium/high."""
    aliases: dict[str, str] = dict(_CONVICTION_EXTRA_ALIASES)
    for wire in _CONVICTION_WIRE_VALUES:
        aliases[wire] = wire
        aliases[wire.lower()] = wire
        aliases[wire.capitalize()] = wire
        for locale_values in _VALUES.values():
            for key in (wire, wire.capitalize()):
                localized = locale_values.get(key)
                if not localized:
                    continue
                aliases[localized] = wire
                aliases[localized.lower()] = wire
    return aliases


def rating_label_spellings() -> tuple[str, ...]:
    """Label spellings that precede a rating / recommendation token in prose."""
    return tuple(iter_label_spellings("rating", "recommendation"))


def _unique_extra(*values: str) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


# Extra label spellings accepted by API decision-field parsers. Kept here so
# ``api/formatters.py`` can stay ASCII-only while still recognizing localized
# chrome produced by the render helpers.
PRICE_TARGET_LABELS: tuple[str, ...] = _unique_extra(
    "Price Target",
    "Target Price",
    "target_price",
    "\u4ef7\u683c\u76ee\u6807",
    *iter_label_spellings("price_target"),
)
CONFIDENCE_LABELS: tuple[str, ...] = _unique_extra(
    "Confidence",
    "confidence",
    *iter_label_spellings("confidence"),
)
REASONING_LABELS: tuple[str, ...] = _unique_extra(
    "Investment Thesis",
    "Reasoning",
    "Executive Summary",
    *iter_label_spellings(
        "investment_thesis",
        "reasoning",
        "executive_summary",
        "rationale",
    ),
)
