# API Endpoints

This file lists current API endpoints and what each one does.

## GET Endpoints

| Method | Endpoint | What it does |
|---|---|---|
| GET | `/` | Returns the home page (`index.html`). |
| GET | `/health` | Health check endpoint; returns `{"status":"ok"}`. |
| GET | `/metrics` | Exposes Prometheus metrics for monitoring. |
| GET | `/<short_code>` | Resolves a short code and redirects to the original URL. Returns 404 if not found, 410 if revoked. |
| GET | `/analytics/<short_code>` | Returns click analytics for a short code. |
| GET | `/<short_code>/analytics` | Alias of `/analytics/<short_code>`. |
| GET | `/users` | Lists users (supports optional pagination via `page` and `per_page`). |
| GET | `/users/<user_id>` | Returns one user by ID. |
| GET | `/events` | Lists events (supports optional filters: `user_id`, `url_id`, `event_type`). |
| GET | `/urls` | Lists URLs (supports optional filters: `user_id`, `is_active`). |
| GET | `/urls/<url_id>` | Returns one URL record by ID. |
| GET | `/urls/<url_id>/analytics` | Returns analytics for a URL record by ID. |

## POST Endpoints

| Method | Endpoint | What it does |
|---|---|---|
| POST | `/shorten` | Creates a short URL from a long URL. Supports optional `custom_alias` and `user_id`. |
| POST | `/revoke` | Revokes an existing short code so it no longer resolves. |
| POST | `/users` | Creates a new user. |
| POST | `/users/bulk` | Bulk imports users from uploaded CSV file. |
| POST | `/events` | Creates a new event (optionally linked to a URL). |
| POST | `/urls` | Creates a URL record with generated short code. |

## PUT Endpoints

| Method | Endpoint | What it does |
|---|---|---|
| PUT | `/users/<user_id>` | Updates a user's editable fields (username/email). |
| PUT | `/urls/<url_id>` | Updates URL fields such as title, active state, and/or original URL. |

## DELETE Endpoints

| Method | Endpoint | What it does |
|---|---|---|
| DELETE | `/<short_code>` | Revokes (deactivates) a short code. |
| DELETE | `/shorten/<short_code>` | Alias to revoke/deactivate a short code. |
| DELETE | `/users/<user_id>` | Deletes a user by ID. |
| DELETE | `/urls/<url_id>` | Deletes a URL record by ID. |

## Notes

- The `/urls` routes are registered with a URL prefix, so handlers in `app/routes/urls.py` are exposed under `/urls/...`.
