# Atlas

מערכת אישית למחקר ומסחר רב-נכסי: מניות, תעודות סל, אג"ח, קריפטו ומט"ח,
בארה"ב, ישראל, אירופה וסין.

> ⚠️ ברירת המחדל היא **מסחר מדומה (paper)**. אין כאן ייעוץ השקעות ואין הבטחה לרווח.

## עקרונות

- המודל (Claude) מנתח ומציע. הקוד מחשב מספרים, ומנוע סיכונים דטרמיניסטי מאשר או דוחה.
- כל טקסט חיצוני (חדשות, דוחות, נאומים) מטופל כמידע לא אמין.
- מתג חירום (kill switch) ועצירה אוטומטית בהפסד יומי או ב-drawdown.

## מה יש כרגע (שלב 1)

| רכיב | קובץ |
|---|---|
| טיפוסי ליבה (נכס, נר, הצעת עסקה, תיק) | `src/atlas/domain.py` |
| מנוע סיכונים וחישוב גודל פוזיציה | `src/atlas/risk/engine.py`, `config/risk.yaml` |
| שעות מסחר לפי בורסה | `src/atlas/calendars.py`, `config/markets.yaml` |
| הגנה מ-prompt injection | `src/atlas/untrusted.py` |
| ממשקי נתונים וספק CSV | `src/atlas/data/` |
| סכמת מסד נתונים | `db/schema.sql` |
| פרומפט האנליסט | `prompts/analyst_system.md` |

## שלב 2

| רכיב | קובץ |
|---|---|
| אינדיקטורים (SMA, EMA, RSI, ATR, Donchian, MACD, Bollinger) | `src/atlas/indicators.py` |
| שתי אסטרטגיות בסיס: פריצת ערוץ, ותיקון בתוך מגמה | `src/atlas/strategies.py` |
| ברוקר מדומה עם עמלות, ספרד והחלקה | `src/atlas/paper.py` |
| backtest, בדיוק לפי אותם כללים של חשבון הדמו | `src/atlas/backtest.py` |
| מערכת למידה אחרי כל עסקה | `src/atlas/learning.py` |
| פרופיל חשבון הדמו (1,000 ₪) | `config/account.yaml` |

```bash
uv run atlas backtest data/SPY_1d.csv --symbol SPY --strategy rsi_pullback
```

## הרצה

```bash
uv sync
uv run pytest
cp .env.example .env
docker compose up -d   # TimescaleDB + Redis
```

מפת הדרכים המלאה נמצאת ב-`CLAUDE.md`.
