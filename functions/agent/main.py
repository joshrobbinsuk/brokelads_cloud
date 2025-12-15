import json
from datetime import datetime


def agent_handler(event, context):
    now = datetime.now().isoformat()
    return {
        "statusCode": 200,
        "body": json.dumps(
            {"message": f"Hello from the agent! It's {str(now)}", "event": event}
        ),
    }
