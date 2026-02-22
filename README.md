# Intercept

Modern cybersecurity case management for security teams. Track incidents, manage alerts, and collaborate on investigations—all in one place.

**Stack:** FastAPI • React • TypeScript • PostgreSQL

## Quick Start

### Prerequisites

- [Conda](https://docs.conda.io/en/latest/miniconda.html) (Python environment)
- [Docker](https://www.docker.com/) (PostgreSQL database)
- [Node.js](https://nodejs.org/) 18+

### Setup

```bash
# Clone and set up environment
git clone https://github.com/tidemark-security/intercept.git
cd intercept
conda env create -f environment.yml
conda activate intercept

# Install frontend dependencies
cd frontend && npm install && cd ..

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env with your settings (SESSION_SECRET_KEY is required)

# Start database and run migrations
docker-compose up -d
cd backend && alembic upgrade head && cd ..
```

### Run

```bash
# Terminal 1: Backend
cd backend && uvicorn app.main:app --reload

# Terminal 2: Frontend  
cd frontend && npm run dev
```

Open [http://localhost:5173](http://localhost:5173) and you're in.

## Project Structure

```
intercept/
├── backend/           # FastAPI API server
├── frontend/          # React TypeScript app
├── scripts/           # Dev utilities
├── langflow/          # Example AI agent configurations
└── docs/              # Additional documentation
```

## Development

### After Changing Backend Models

Regenerate TypeScript types to keep frontend in sync:

```bash
./scripts/generate-types.sh
```

### Key Documentation

- [MCP Integration Guide](docs/mcp-integration-guide.md) — Connect AI tools to Intercept
- [Search Architecture](docs/search-architecture.md) — How search works
- [Task Queue](docs/task-queue.md) — Background job processing

## Features

- **Case Management** — Create, assign, and track security incidents
- **Alert Triage** — Ingest and prioritize alerts from multiple sources
- **Timeline Views** — Visualize incident progression
- **AI Chat Assistant** — LangFlow-powered investigation helper
- **MITRE ATT&CK Mapping** — Tag cases with tactics and techniques
- **Role-Based Access** — Admin, Analyst, and Viewer roles
- **Audit Logging** — Full activity trail for compliance

## License

[MIT](LICENSE)
