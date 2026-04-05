from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "app_requests_total",
    "Total number of HTTP requests handled by the application",
    ["method", "path", "status_code"],
)

ERROR_COUNT = Counter(
    "app_errors_total",
    "Total number of HTTP 5xx responses and unhandled exceptions",
)

REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds",
    "Request latency in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def _path_label(request):
    rule = getattr(request, "url_rule", None)
    if rule is not None:
        return rule.rule
    return request.path


def record_request_metrics(request, response, latency_ms):
    path = _path_label(request)
    status_code = response.status_code

    REQUEST_COUNT.labels(
        method=request.method,
        path=path,
        status_code=str(status_code),
    ).inc()

    if latency_ms is not None:
        REQUEST_LATENCY.labels(method=request.method, path=path).observe(latency_ms / 1000.0)

    if status_code >= 500:
        ERROR_COUNT.inc()


def record_exception():
    ERROR_COUNT.inc()
