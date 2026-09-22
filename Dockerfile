# Builds the React frontend, then serves it and the API from one Python container.
# Local development does not use this file — see README.md for the two-server dev setup.

FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS backend
WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY backend/ backend/
RUN pip install --no-cache-dir -e backend

COPY testdata/ testdata/
COPY --from=frontend-build /app/frontend/dist frontend/dist

ENV FINIO_DB=/app/data/finio.sqlite3
ENV FINIO_SEED_DEMO_DATA=1

EXPOSE 8000
CMD ["uvicorn", "finio.main:app", "--host", "0.0.0.0", "--port", "8000"]
