# Build do front (React/Vite) e imagem final só com Python: o FastAPI entrega o frontend/dist.

FROM node:20-alpine AS front
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AMBIENTE=producao
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=front /app/frontend/dist /app/frontend/dist
# Roda sem permissão de administrador (root) dentro do contêiner.
RUN useradd --create-home --uid 10001 app
USER app
# O Render informa a porta na variável PORT.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
