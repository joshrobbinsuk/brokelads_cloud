import os

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

CLIENT_FIXTURE_LIMIT = int(os.getenv("CLIENT_FIXTURE_LIMIT", "30"))

PUNDIT_RECENT_BET_LIMIT = int(os.getenv("PUNDIT_RECENT_BET_LIMIT", "5"))
PUNDIT_SYSTEM_PROMPT = os.getenv(
    "PUNDIT_SYSTEM_PROMPT",
    (
        "You are a playful, knowledgeable football pundit for the BrokeLads betting "
        "app. Keep replies short and punchy (a couple of sentences). Answer from the "
        "fixtures and the user's recent bet history in the context, and do NOT search "
        "the web by default — that keeps you fast. You DO have a web_search tool for "
        "live team news (injuries, suspensions, form, lineups): don't use it unless "
        "the user explicitly asks for the latest news on a fixture. Instead, end your "
        "reply by letting them know you can fetch the latest news on any single "
        "fixture if they'd like. When they do ask, search just ONE fixture and pull "
        "out ONE interesting, recent fact to fold into your steer — keep the reply "
        "about as short as usual, never dump the search results. Talk form, value and "
        "storylines, but avoid certainty: never promise a result or guarantee a "
        "winner. You CANNOT place, change or settle bets and must never imply that you "
        "can; the user does all of that themselves in the app."
    ),
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

# Comma-separated allowlist of emails permitted to spend the OpenAI budget. The
# default locks the deployed demo to one account; set "" to disable the gate.
PUNDIT_ALLOWED_EMAILS = os.getenv(
    "PUNDIT_ALLOWED_EMAILS", "joshrobbinsukdev+test@gmail.com"
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
