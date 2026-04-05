import json
import logging
import os
import socket
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "message": record.getMessage(),
            "node_id": os.environ.get("NODE_ID", socket.gethostname()),
        }

        # Promote common structured extras when present.
        for field in (
            "method",
            "path",
            "status_code",
            "latency_ms",
            "request_id",
            "short_code",
            "user_id",
            "url_id",
        ):
            value = getattr(record, field, None)
            if value is not None:
                event[field] = value

        if record.exc_info:
            event["exception"] = self.formatException(record.exc_info)

        return json.dumps(event)


def configure_structured_logging():
    root = logging.getLogger()

    # Avoid duplicate handlers if app factory is called multiple times in tests.
    root.handlers.clear()
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Keep framework loggers flowing through root JSON formatter.
    logging.getLogger("werkzeug").handlers.clear()
    logging.getLogger("werkzeug").propagate = True
