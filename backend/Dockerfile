FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

EXPOSE 8000

# Honour $PORT when the platform sets one, fall back to 8000 when it does not.
#
# Railway, Render, Cloud Run and Fly all assign a port at runtime and route to it; a
# container that listens on a hardcoded 8000 is simply unreachable there, and the failure
# looks like a health-check timeout rather than anything pointing at the port. The shell
# form is required — exec form does no variable expansion, so "$PORT" would be passed to
# uvicorn as a literal string. Local `docker compose up` sets no PORT and keeps 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
