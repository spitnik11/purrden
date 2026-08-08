# Phase 1: multi-stage static PWA image (no backend).
# Build from monorepo root:
#   docker build -f deploy/containers/web.Dockerfile -t purrden-web .

FROM node:20-alpine AS build
WORKDIR /src

# Content + shared packages needed by Vite aliases
COPY content ./content
COPY packages/spawn-engine-js ./packages/spawn-engine-js
COPY packages/domain-ts ./packages/domain-ts
COPY apps/web/package.json apps/web/package-lock.json ./apps/web/
WORKDIR /src/apps/web
RUN npm ci

COPY apps/web ./
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY deploy/containers/web.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/apps/web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz || exit 1
