# In Case of Emergency Runbook

This guide is the first 5 minutes of response when an alert fires. Use the dashboard first, then logs, then the control plane. Do not start by changing code.

## 1. Identify the alert

Open Prometheus alerts:

- `http://localhost:9090/alerts`

Look for:

- `ServiceDown`
- `HighErrorRate`

Record:

- Alert name
- Start time
- Severity
- Whether it is still firing or already resolved

## 2. Check the dashboard

Open Grafana:

- `http://localhost:3000`

Use the Watchtower dashboard and check these panels:

- Traffic
- Errors
- Latency
- Saturation

Decision guide:

- Traffic flat at zero and ServiceDown firing: the app or scrape path is down.
- Errors spiking and traffic still present: the app is alive but failing requests.
- Latency rising with normal traffic: the app is overloaded or blocked.
- CPU or memory saturation rising: the app may be resource constrained.

## 3. Check logs without SSH

Use Docker logs from your workstation:

```bash
docker compose logs --tail=100 app
```

Useful additions:

```bash
docker compose logs --tail=100 prometheus
docker compose logs --tail=100 alertmanager
```

What to look for:

- JSON logs with `level`, `timestamp`, and `component`
- `error` or `exception` messages
- repeated request failures
- Redis or database connection failures
- Alertmanager delivery errors

## 4. Decide the likely failure mode

### If `ServiceDown` is firing

- Confirm the app container is running:

```bash
docker compose ps app
```

- If the app is stopped, start it:

```bash
docker compose start app
```

- If it is running but Prometheus still shows `up{job="app"} == 0`, inspect the app logs for startup or binding errors.

### If `HighErrorRate` is firing

- Check the app logs for the most recent failing request type.
- Confirm whether the failures are concentrated in `/shorten`, `/health`, or redirect paths.
- Use the dashboard to see whether error spikes line up with latency spikes.

### If traffic is zero but the app is healthy

- Verify the load test or demo traffic is actually running.
- Confirm Prometheus is scraping the app:

```bash
curl -s http://localhost:5000/metrics | head
```

- Confirm the app logs show requests being handled.

## 5. Fix the smallest thing first

Prefer the least invasive recovery step:

- Restart the app container if it crashed.
- Restart Prometheus if it is stale.
- Restart Alertmanager if notifications are not flowing.
- Only touch code if the logs prove the app behavior is broken.

## 6. Confirm recovery

After the fix:

- `ServiceDown` should resolve.
- `HighErrorRate` should stop increasing.
- Traffic and latency should return to normal on Grafana.
- Alertmanager should send a resolved notification if configured.

## Sherlock Mode Exercise

Use only the dashboard and logs to diagnose the issue.

### Fake issue

The dashboard shows:

- Traffic is normal
- Errors are rising fast
- Latency is also rising
- CPU is high, memory is stable

### What to do

1. Open Grafana and look at the Watchtower dashboard.
2. Pick the first panel that moved away from baseline.
3. Open app logs:

```bash
docker compose logs --tail=100 app
```

4. Find the first repeated error line.
5. Match the log pattern to the dashboard pattern.

### Sherlock steps

1. Open Grafana and confirm which panel changed first.
2. Open `docker compose logs --tail=100 app`.
3. Find the first repeated error message.
4. Decide whether the root cause is:
   - upstream dependency failure
   - bad input spike
   - resource pressure
   - configuration regression

### Ready-made demo scenarios

#### Scenario 1: ServiceDown

Run:

```bash
docker compose stop app
```

What you should see:

- Prometheus alert: `ServiceDown`
- Grafana traffic flat at zero
- App logs stop updating or show startup failures

#### Scenario 2: HighErrorRate

Trigger a real server failure, then hit a DB-backed route.

Example:

```bash
docker compose stop db
curl -i http://localhost:5001/users
curl -i http://localhost:5001/users
```

What you should see:

- Prometheus alert: `HighErrorRate`
- Grafana errors rising
- App logs filled with repeated 500-level errors or database failures

Restore the database:

```bash
docker compose start db
```

#### Scenario 3: Latency spike

Run the load test or a heavier request burst.

Example:

```bash
K6_DIRECT_APP=1 BASE_URL=http://127.0.0.1:5001 TARGET_VUS=25 k6 run k6/load.js
```

What you should see:

- Grafana latency rises first
- CPU panel rises with load
- App logs still show successful requests, but slower

### Example conclusion

- If logs show repeated Redis or database connection failures, the app is healthy enough to accept traffic but failing on a downstream dependency.
- If logs show validation errors only, the alert is likely caused by a bad client request spike, not an outage. Validation errors do not trigger `HighErrorRate` in this stack.
- If logs show timeouts and CPU is high, the app is probably overloaded.

### Demo script

1. Open Grafana.
2. Point to the panel that changed.
3. Open app logs.
4. Read the first repeated error line aloud.
5. State the likely root cause and the smallest next action.

## Quick commands

```bash
docker compose ps

docker compose logs --tail=100 app

docker compose logs --tail=100 prometheus

docker compose logs --tail=100 alertmanager
```
