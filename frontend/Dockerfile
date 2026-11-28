FROM nginx:1.31.9-alpine-slim AS nginx-base

RUN apk upgrade --no-cache

FROM node:24.22.3-trixie-slim AS build

RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global npm@11.21.3 --no-audit --no-fund

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Copy source code and config files
COPY index.html tsconfig.json tsconfig.node.json vite.config.ts tailwind.config.js postcss.config.js ./
COPY src/ src/
COPY public/ public/

# Build production bundle (skip tsc — type checking is done in CI)
RUN npx vite build

# --- Production stage ---
FROM nginx-base

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN sed -i 's|pid        /run/nginx.pid;|pid        /tmp/nginx.pid;|' /etc/nginx/nginx.conf \
    && chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/run /etc/nginx/conf.d

EXPOSE 8080

USER nginx

CMD ["nginx", "-g", "daemon off;"]
