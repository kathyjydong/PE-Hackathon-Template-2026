#This file Dockerfile is used as a blueprint to create each container for scaling.


# Tell it which python to load, online docs recommend python 3.12-slim
FROM python:3.12-slim

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

# This is what actually runs the code within the contianer when it wakes up. 
# It uses uv and gunicorn so instead of waiting in a line to run the code, 
# it can run multiple instances of the code at the same time and handle multiple requests at the same time. 
CMD ["uv", "run", "gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "run:app"]