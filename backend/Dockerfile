# One image for every backend process: `ingest`, `api`, `migrate`, later `worker`.
FROM python:3.11-slim AS build
WORKDIR /src
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir build && python -m build --wheel

FROM python:3.11-slim
RUN useradd --system --uid 10001 --no-create-home smarthive
COPY --from=build /src/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
USER 10001
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
ENTRYPOINT ["smarthive"]
CMD ["ingest"]
