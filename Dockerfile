FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/index.html frontend/vite.config.ts frontend/tsconfig*.json ./
COPY frontend/src ./src
COPY frontend/tunnel ./tunnel
COPY frontend/public ./public
RUN pnpm build

FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings_staging
WORKDIR /app
COPY requirements-staging.txt ./
RUN pip install --no-cache-dir -r requirements-staging.txt
COPY manage.py ./
COPY config ./config
COPY shop ./shop
COPY storefront ./storefront
COPY deploy ./deploy
COPY --from=frontend /build/frontend/dist ./frontend/dist
RUN python deploy/collect_frontend.py && python manage.py collectstatic --noinput --settings=config.settings_build
RUN useradd --create-home app && chown -R app:app /app
USER app
CMD ["sh", "deploy/start.sh"]
