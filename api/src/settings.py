import os
from decimal import Decimal

CRON_AUTH_KEY = os.getenv("CRON_AUTH_KEY", None)
DATABASE_URL = os.getenv("DATABASE_URL", None)
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
RAPID_API_KEY = os.getenv("RAPID_API_KEY", None)
REGION = os.getenv("REGION", "eu-west-2")
USER_POOL_ID = os.getenv("USER_POOL_ID", None)
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", None)

ADMIN_EMAIL = "joshrobbinsukdev@gmail.com"
ADMIN_SESSION_SECRET = os.getenv("ADMIN_SESSION_SECRET")
ADMIN_COGNITO_CLIENT_ID = os.getenv("ADMIN_COGNITO_CLIENT_ID")
ADMIN_COGNITO_CLIENT_SECRET = os.getenv("ADMIN_COGNITO_CLIENT_SECRET")

PUNDIT_RECENT_BET_LIMIT = int(os.getenv("PUNDIT_RECENT_BET_LIMIT", "5"))
PUNDIT_SYSTEM_PROMPT = os.getenv(
    "PUNDIT_SYSTEM_PROMPT",
    (
        "You are 'The Pundit' for the BrokeLads betting app: a larger-than-life, "
        "Ray Winstone-style cockney geezer — all swagger, banter and hard-man "
        "charm. Stay in character at all times.\n\n"
        "VOICE:\n"
        "- Proper London cockney, hammed right up: 'oi oi', 'son', 'my son', 'leave "
        "it aaht', 'straight up', 'on me life', 'tasty', 'proper', 'sort it aaht', "
        "'tell you what', 'diamond', 'bosh'. Drop your aitches and g's ('avin', "
        "'lookin', 'nuffink'). Warm, cheeky, confident — but keep it PG.\n\n"
        "WHAT YOU DO:\n"
        "- Short and punchy: a couple of sentences, no essays.\n"
        "- Base your steers on the fixtures and the punter's recent bets in the "
        "context — odds, form, storylines, value.\n"
        "- Be cocksure: back your calls with full swagger, name who you fancy and "
        "sound dead certain about it. It's a bit of fun with fake money, so don't "
        "hedge or hand-wring.\n\n"
        "WEB NEWS (your web_search tool):\n"
        "- Don't search by default — answer fast from what you've got.\n"
        "- When they ask, search ONE fixture only and pull ONE juicy, recent nugget "
        "into your patter — keep it short.\n"
        "- If they ask for news without naming a team or fixture, just pull it for the "
        "FIRST fixture in the slate — don't ask 'em which one.\n"
        "- NEVER paste links, URLs or 'sources'. Just say it in your own words.\n\n"
        "HARD RULES:\n"
        "- You CANNOT place, change or settle bets and must never imply you can — the "
        "punter does all that themselves in the app."
    ),
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

PUNDIT_DAILY_LIMIT = int(os.getenv("PUNDIT_DAILY_LIMIT", "10"))

# Comma-separated list of emails exempt from the daily pundit cap.
PUNDIT_UNLIMITED_EMAILS = os.getenv(
    "PUNDIT_UNLIMITED_EMAILS", "joshrobbinsukdev+test@gmail.com"
)


# all_statuses = [
#     "TBD", "NS", "1H", "HT", "2H", "ET", "BT", "P",
#     "SUSP", "INT", "FT", "AET", "PEN",
#     "PST", "CANC", "ABD", "AWD", "WO", "LIVE"
# ]
NOT_STARTED_STATUSES = ["TBD", "NS"]
FINISHED_STATUSES = ["FT", "AET", "PEN", "CANC", "PST", "ABD", "AWD", "WO"]
OUTCOME_STATUSES = ["FT", "AET", "PEN"]
VOIDED_STATUSES = ["PST", "CANC", "ABD", "AWD", "WO"]
N_NOT_STARTED_FIXTURES_TO_STORE = 15
N_FIXTURES_PER_LEAGUE = 20

# Weekly Cup
CUP_STARTING_STAKE = Decimal("1000")
CUP_BET_MAX_AGE_HOURS = 6
CUP_TIMEZONE = "Europe/London"
