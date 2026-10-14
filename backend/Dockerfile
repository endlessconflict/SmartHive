FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY src ./src
RUN pip install --no-cache-dir .
EXPOSE 8000
# Migrate, then serve. One replica in Prototype 1, so no migration race.
CMD ["sh", "-c", "alembic upgrade head && uvicorn smarthive.api.main:app --host 0.0.0.0 --port 8000"]
