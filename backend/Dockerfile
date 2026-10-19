# One image for every backend process: `ingest`, `api`, `migrate`, later `worker`.
FROM python:3.11-slim AS build
WORKDIR /src
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir build && python -m build --wheel

FROM python:3.11-slim
# pg_dump and pg_restore for `smarthive backup`; the major version must match the database server (16)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg     && install -d /usr/share/keyrings     && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg     && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main"        > /etc/apt/sources.list.d/pgdg.list     && apt-get update && apt-get install -y --no-install-recommends postgresql-client-16     && apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --no-create-home smarthive
COPY --from=build /src/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
USER 10001
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
ENTRYPOINT ["smarthive"]
CMD ["ingest"]
