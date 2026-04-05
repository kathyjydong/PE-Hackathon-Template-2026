# MLH PE Hackathon — Flask + Peewee + PostgreSQL Template

A minimal hackathon starter template. You get the scaffolding and database wiring — you build the models, routes, and CSV loading logic.

**Stack:** Flask · Peewee ORM · PostgreSQL · uv

## **Important**

You need to work with around the seed files that you can find in [MLH PE Hackathon](https://mlh-pe-hackathon.com) platform. This will help you build the schema for the database and have some data to do some testing and submit your project for judging. If you need help with this, reach out on Discord or on the Q&A tab on the platform.

## Prerequisites

- **uv** — a fast Python package manager that handles Python versions, virtual environments, and dependencies automatically.
  Install it with:
  ```bash
  # macOS / Linux
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Windows (PowerShell)
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
  For other methods see the [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/).
- PostgreSQL running locally (you can use Docker or a local instance)

## uv Basics

`uv` manages your Python version, virtual environment, and dependencies automatically — no manual `python -m venv` needed.

| Command | What it does |
|---------|--------------|
| `uv sync` | Install all dependencies (creates `.venv` automatically) |
| `uv run <script>` | Run a script using the project's virtual environment |
| `uv add <package>` | Add a new dependency |
| `uv remove <package>` | Remove a dependency |

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url> && cd mlh-pe-hackathon

# 2. Install dependencies
uv sync

# 3. Create the database
createdb hackathon_db

# 4. Configure environment
cp .env.example .env   # edit if your DB credentials differ

# 5. Run the server
uv run run.py

# 6. Verify
curl http://localhost:5000/health
# → {"status":"ok"}
```

## Project Structure

```
mlh-pe-hackathon/
├── app/
│   ├── __init__.py          # App factory (create_app)
│   ├── database.py          # DatabaseProxy, BaseModel, connection hooks
│   ├── models/
│   │   └── __init__.py      # Import your models here
│   └── routes/
│       └── __init__.py      # register_routes() — add blueprints here
├── .env.example             # DB connection template
├── .gitignore               # Python + uv gitignore
├── .python-version          # Pin Python version for uv
├── pyproject.toml           # Project metadata + dependencies
├── run.py                   # Entry point: uv run run.py
└── README.md
```

## How to Add a Model

1. Create a file in `app/models/`, e.g. `app/models/product.py`:

```python
from peewee import CharField, DecimalField, IntegerField

from app.database import BaseModel


class Product(BaseModel):
    name = CharField()
    category = CharField()
    price = DecimalField(decimal_places=2)
    stock = IntegerField()
```

2. Import it in `app/models/__init__.py`:

```python
from app.models.product import Product
```

3. Create the table (run once in a Python shell or a setup script):

```python
from app.database import db
from app.models.product import Product

db.create_tables([Product])
```

## How to Add Routes

1. Create a blueprint in `app/routes/`, e.g. `app/routes/products.py`:

```python
from flask import Blueprint, jsonify
from playhouse.shortcuts import model_to_dict

from app.models.product import Product

products_bp = Blueprint("products", __name__)


@products_bp.route("/products")
def list_products():
    products = Product.select()
    return jsonify([model_to_dict(p) for p in products])
```

2. Register it in `app/routes/__init__.py`:

```python
def register_routes(app):
    from app.routes.products import products_bp
    app.register_blueprint(products_bp)
```

## How to Load CSV Data

```python
import csv
from peewee import chunked
from app.database import db
from app.models.product import Product

def load_csv(filepath):
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    with db.atomic():
        for batch in chunked(rows, 100):
            Product.insert_many(batch).execute()
```

## Useful Peewee Patterns

```python
from peewee import fn
from playhouse.shortcuts import model_to_dict

# Select all
products = Product.select()

# Filter
cheap = Product.select().where(Product.price < 10)

# Get by ID
p = Product.get_by_id(1)

# Create
Product.create(name="Widget", category="Tools", price=9.99, stock=50)

# Convert to dict (great for JSON responses)
model_to_dict(p)

# Aggregations
avg_price = Product.select(fn.AVG(Product.price)).scalar()
total = Product.select(fn.SUM(Product.stock)).scalar()

# Group by
from peewee import fn
query = (Product
         .select(Product.category, fn.COUNT(Product.id).alias("count"))
         .group_by(Product.category))
```

## Tips

- Use `model_to_dict` from `playhouse.shortcuts` to convert model instances to dictionaries for JSON responses.
- Wrap bulk inserts in `db.atomic()` for transactional safety and performance.
- The template uses `teardown_appcontext` for connection cleanup, so connections are closed even when requests fail.
- Check `.env.example` for all available configuration options.

## Error Handling

The app returns JSON errors for common HTTP failures:

- `404 Not Found`: returned when a route does not exist (including unknown short codes).
    Response body:
    ```json
    {"error": "Not found"}
    ```

- `500 Internal Server Error`: returned when an unhandled server exception occurs.
    Response body:
    ```json
    {"error": "Internal server error"}
    ```

Example checks:

```bash
curl -i http://localhost:5000/does-not-exist
# HTTP/1.1 404

curl -i http://localhost:5000/some-missing-short-code
# HTTP/1.1 404
```

## Failure Modes

For the full graceful-failure behavior, chaos testing steps, and live demo checklist, see [Failure Modes](docs/failure-modes.md).

## Kafka Log Streaming (Tier 1 Bronze)

The app now emits structured JSON logs to stdout. You can pipe those logs directly to Kafka so logs are centralized and visible without SSH.

Example JSON log event:

```json
{
    "timestamp": "2026-04-04T20:05:00+00:00",
    "level": "INFO",
    "component": "api",
    "message": "Request completed",
    "node_id": "server-01",
    "method": "GET",
    "path": "/health",
    "status_code": 200,
    "latency_ms": 2.14
}
```

### 1. Create/verify the Kafka topic

```bash
BOOTSTRAP_SERVER=localhost:9092 ./scripts/create-kafka-topic.sh app-logs
```

### 2. Stream app logs to Kafka

```bash
TOPIC_NAME=app-logs BOOTSTRAP_SERVER=localhost:9092 ./scripts/stream-logs-to-kafka.sh
```

### 3. Consume logs from another terminal/machine

```bash
TOPIC_NAME=app-logs BOOTSTRAP_SERVER=<server-ip>:9092 FROM_BEGINNING=true ./scripts/consume-kafka-logs.sh
```

### Optional environment knobs

- `NODE_ID`: identifier included in every JSON log event.
- `LOG_LEVEL`: logger threshold (default `INFO`).
- `APP_CMD`: command used by stream script (default `uv run run.py`).

## Local Watchtower Metrics (Tier 2 + Tier 3)

This template now exposes Prometheus metrics at `/metrics` and includes local Prometheus + Grafana services for alerting and dashboards.

### What gets exported

- `app_requests_total`: request traffic count (labels: method, path, status_code)
- `app_request_latency_seconds`: request latency histogram (labels: method, path)
- `app_errors_total`: count of server errors (`5xx`) and unhandled exceptions
- Default Python process metrics from `prometheus_client` (CPU and memory)

### Start the watchtower stack

```bash
docker compose up --build -d db app prometheus grafana
```

### URLs

- App health: `http://localhost:5000/health`
- Raw metrics: `http://localhost:5000/metrics`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (default login: `admin` / `admin`)

### Alert trap: High Error Rate

Prometheus rule file: `monitoring/prometheus/alert-rules.yml`

Current rules:

```promql
up{job="app"} == 0
increase(app_errors_total[1m]) > 5
```

These are evaluated every 10s. You can view alert state in Prometheus under Alerts.

### Alert delivery channel (Silver)

This project includes Alertmanager and forwards alerts to a webhook channel (Discord/Slack webhook URL).

1. Set your webhook URL in `.env` (this file is gitignored):

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/<id>/<token>
```

2. Start monitoring stack:

```bash
docker compose up --build -d app prometheus alertmanager grafana
```

3. Open UIs:

- Prometheus Alerts: `http://localhost:9090/alerts`
- Alertmanager: `http://localhost:9093`

### Fire drill (Silver demo in <5 minutes)

Trigger `ServiceDown`:

```bash
docker compose stop app
```

Expected:

- `ServiceDown` enters firing state after ~1 minute.
- Notification arrives in your webhook channel.

Restore service:

```bash
docker compose start app
```

### Golden Signals dashboard

Grafana auto-loads `Watchtower - Golden Signals` from:

- `monitoring/grafana/dashboards/watchtower-golden-signals.json`

Panels included:

- Traffic: `sum(rate(app_requests_total[1m]))`
- Errors: `sum(rate(app_errors_total[1m]))`
- Latency: p95 from `app_request_latency_seconds_bucket`
- Saturation: process CPU + resident memory
