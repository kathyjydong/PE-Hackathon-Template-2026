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

# gthread: many concurrent I/O-bound requests per process (Redis resolve). Tune via env.
ENV GUNICORN_WORKER_CLASS=gthread
ENV GUNICORN_WORKERS=4
ENV GUNICORN_THREADS=96
ENV GUNICORN_MAX_CONCURRENCY=512
ENV DATABASE_POOL_MAX=4
ENV GUNICORN_BACKLOG=2048
ENV GUNICORN_TIMEOUT=120
CMD sh -c 'mkdir -p /tmp/prometheus && exec uv run gunicorn -c gunicorn_conf.py run:app'