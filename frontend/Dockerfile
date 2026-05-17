FROM node:24-slim AS build

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy package.json only — lockfile references local ../ux path from
# dev/docker-compose.yml dev setup which isn't available in CI.
# package.json has the correct git+https URL for @tidemark-security/ux.
COPY package.json ./

# Install all dependencies (including devDependencies for build)
RUN npm install --no-audit --no-fund

# Copy source code and config files
COPY index.html tsconfig.json tsconfig.node.json vite.config.ts tailwind.config.js postcss.config.js ./
COPY src/ src/

# Build production bundle (skip tsc — type checking is done in CI)
RUN npx vite build

# --- Production stage ---
FROM nginx:alpine

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN sed -i 's|pid        /run/nginx.pid;|pid        /tmp/nginx.pid;|' /etc/nginx/nginx.conf \
    && chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/run /etc/nginx/conf.d

EXPOSE 8080

USER nginx

CMD ["nginx", "-g", "daemon off;"]
