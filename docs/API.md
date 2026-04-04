# API Documentation

Base URL (local): `http://localhost`

## Health

### GET /health
Checks whether the API is running.

- Success: `200 OK`
- Response:

```json
{
	"status": "ok"
}
```

## URL Shortener

### POST /shorten
Creates a short URL from a long URL.

- Request body:

```json
{
	"url": "https://example.com/page",
	"custom_alias": "optional_alias"
}
```

- Notes:
	- `url` is required.
	- `custom_alias` is optional.
	- Alias must be 3-32 chars using letters, numbers, `_`, or `-`.

- Success:
	- `200 OK` when an existing active mapping is reused
	- `201 Created` when a new short URL is created

- Response:

```json
{
	"short_url": "http://localhost/abc123"
}
```

### POST /revoke
Revokes an existing short code so it no longer redirects.

- Request body:

```json
{
	"short_code": "abc123"
}
```

- Success: `200 OK`
- Response:

```json
{
	"short_code": "abc123",
	"revoked": true
}
```

### GET /<short_code>
Resolves and redirects a short code to the original URL.

- Success: `302 Found` (redirect)
- Not found: `404 Not Found`
- Revoked: `410 Gone`

## Users

### GET /users
Returns all users.

- Optional query params:
	- `page` (int)
	- `per_page` (int)

- Success: `200 OK`
- Response:

```json
[
	{
		"id": 1,
		"username": "alice",
		"email": "alice@example.com",
		"created_at": "2026-04-04T22:00:00"
	}
]
```

### GET /users/<id>
Returns one user by ID.

- Success: `200 OK`
- Not found: `404 Not Found`

### POST /users
Creates a new user.

- Request body:

```json
{
	"username": "testuser",
	"email": "test@example.com"
}
```

- Success: `201 Created`
- Validation error: `400 Bad Request`
- Conflict (duplicate username/email): `409 Conflict`

### PUT /users/<id>
Updates user fields.

- Request body (one or both fields):

```json
{
	"username": "updated_name",
	"email": "updated@example.com"
}
```

- Success: `200 OK`
- Validation error: `400 Bad Request`
- Conflict (duplicate username/email): `409 Conflict`
- Not found: `404 Not Found`

### POST /users/bulk
Bulk-imports users from a CSV file upload.

- Content type: `multipart/form-data`
- Field name: `file`
- Required CSV headers: `username,email`

- Success: `201 Created`
- Response:

```json
{
	"count": 2
}
```

