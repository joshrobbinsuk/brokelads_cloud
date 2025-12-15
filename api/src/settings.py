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
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")


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
