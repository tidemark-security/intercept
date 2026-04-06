FROM node:24-slim AS build

WORKDIR /app

# Copy package.json only — lockfile references local ../ux path from
# docker-compose dev setup which isn't available in CI.
# package.json has the correct git+https URL for @tidemark-security/ux.
COPY package.json ./

# Install all dependencies (including devDependencies for build)
RUN npm install

# Copy source code and config files
COPY index.html tsconfig.json tsconfig.node.json vite.config.ts tailwind.config.js postcss.config.js ./
COPY src/ src/

# Build production bundle
RUN npm run build

# --- Production stage ---
FROM nginx:alpine

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
