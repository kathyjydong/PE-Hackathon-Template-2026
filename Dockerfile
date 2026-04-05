#This file Dockerfile is used as a blueprint to create each container for scaling.


# Tell it which python to load, online docs recommend python 3.12-slim
FROM python:3.13-slim

# This installs uv into the container
# given to me by gemini
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# This creates the /app folder within the container
WORKDIR /app


# Copy the pyproject.toml to get all the dependencies stated
# this uv sync install all the necessary dependencies (similar to npm i) 
COPY pyproject.toml .
RUN uv sync

# This line copies the rest of the code into container
COPY . .

# Gunicorn: sync workers; each worker handles one request at a time. Under k6 (500+ VUs), -w 4
# causes massive queueing and ~50%+ failures — scale workers (and backlog) with GUNICORN_WORKERS.
ENV GUNICORN_WORKERS=64
ENV GUNICORN_BACKLOG=2048
ENV GUNICORN_TIMEOUT=120
# shell form so env vars expand
CMD sh -c 'exec uv run gunicorn -w "${GUNICORN_WORKERS}" --backlog "${GUNICORN_BACKLOG}" --timeout "${GUNICORN_TIMEOUT}" -b 0.0.0.0:5000 run:app'