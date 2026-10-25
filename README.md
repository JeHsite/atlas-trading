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

## הרצה

```bash
uv sync
uv run pytest
cp .env.example .env
docker compose up -d   # TimescaleDB + Redis
```

מפת הדרכים המלאה נמצאת ב-`CLAUDE.md`.
