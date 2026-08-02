#!/bin/bash

# TypeScript Type Generation Script
# This script generates TypeScript types from the FastAPI backend's OpenAPI specification

set -e  # Exit on any error

echo "🚀 Starting TypeScript type generation..."

# Ensure we're in project root
if [ ! -f "VERSION" ]; then
    echo "❌ Error: This script must be run from the project root directory"
    exit 1
fi

# Check for required tooling
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Error: Python 3 is required but not found"
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "❌ Error: Node.js and npm are required but not found"
    exit 1
fi

# Activate the shared project environment when the caller has not already done
# so. Conda is commonly a shell function, which is not inherited by this child
# process, so avoid trying to rediscover it when the environment is active.
if [ "${CONDA_DEFAULT_ENV:-}" != "intercept" ]; then
    if ! command -v conda >/dev/null 2>&1; then
        echo "❌ Error: activate the 'intercept' Conda environment before running this script"
        exit 1
    fi
    eval "$(conda shell.bash hook)"
    conda activate intercept
fi

# Ensure frontend dependencies exist (install if missing)
if [ ! -d "frontend/node_modules" ]; then
    echo "📥 Installing frontend dependencies..."
    (cd frontend && npm install)
fi

# Generate types from live FastAPI OpenAPI definition
echo "� Generating types from backend OpenAPI..."
python3 scripts/generate-types.py

echo "✅ Type generation complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Review generated types under frontend/src/types/generated/"
echo "   2. Import AuthContracts for contract-driven frontend work"
echo "   3. Remove any superseded handcrafted types"
echo ""
echo "💡 To regenerate types after API changes, run:"
echo "   ./scripts/generate-types.sh"
