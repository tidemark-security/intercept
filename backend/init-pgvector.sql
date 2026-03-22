-- Enable pgvector extension in langflow_rag database
-- This script runs after init.sql and init-pgcron.sql

\c langflow_rag
CREATE EXTENSION IF NOT EXISTS vector;
