-- Database initialization script for Tidemark Intercept
-- This script runs ONCE when the postgres volume is first created.
-- It sets up extensions and creates the Langflow user/databases.
-- All table/index/trigger creation is handled by Alembic migrations.

-- Create Langflow user and database with separate credentials
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'langflow_user') THEN
        CREATE ROLE langflow_user WITH LOGIN PASSWORD 'langflow_password';
    END IF;
END
$$;

SELECT 'CREATE DATABASE langflow OWNER langflow_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langflow')\gexec

SELECT 'CREATE DATABASE langflow_rag OWNER langflow_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langflow_rag')\gexec

-- Grant privileges to langflow_user on both databases
GRANT ALL PRIVILEGES ON DATABASE langflow TO langflow_user;
GRANT ALL PRIVILEGES ON DATABASE langflow_rag TO langflow_user;

-- Create extensions for the main database (intercept_case_db)
-- These are required by Alembic migrations for search and other features
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS vector;
