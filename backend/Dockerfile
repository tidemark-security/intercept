FROM node:24.22.3-trixie-slim AS mermaid-validator

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* \
    && npm install --global npm@11.21.3 --no-audit --no-fund

WORKDIR /opt/mermaid-validator

COPY scripts/mermaid-validator/package.json scripts/mermaid-validator/package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund

COPY scripts/mermaid-validator/validate_mermaid_syntax.mjs ./

FROM python:3.11.18-slim-trixie

WORKDIR /app

COPY requirements.txt .

# Keep the compiler available while building Python wheels.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gcc \
    libmagic1 \
    libstdc++6 \
    postgresql-client \
    && python -m pip install --no-cache-dir --upgrade pip==26.3 setuptools==84.2.1 \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc \
    && rm -rf /var/lib/apt/lists/*

COPY --from=mermaid-validator /usr/local/bin/node /usr/local/bin/node
COPY --from=mermaid-validator /opt/mermaid-validator /opt/mermaid-validator

COPY . .

# Copy and set entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && useradd --create-home --uid 10001 intercept \
    && chown -R intercept:intercept /app /entrypoint.sh

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

EXPOSE 8000

USER intercept

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
