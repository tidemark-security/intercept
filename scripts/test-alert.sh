#!/bin/bash
# A simple script to create a test alert via the backend API.
# Usage: ./test-alert.sh [Title] [Description]

API_URL="${API_URL:-http://localhost:8000/api/v1/alerts}"

if [ -z "$INTERCEPT_API_KEY" ]; then
  echo "Error: INTERCEPT_API_KEY environment variable is not set."
  echo "Usage: INTERCEPT_API_KEY=\"your_key\" ./test-alert.sh [Title] [Description]"
  exit 1
fi

API_KEY="$INTERCEPT_API_KEY"

TITLE="${1:-Test Alert from test-alert.sh}"
DESCRIPTION="${2:-This is a test alert created via the test-alert.sh script.}"

echo "Creating alert: \"$TITLE\"..."

curl -s -X POST "$API_URL" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "'"$TITLE"'",
    "description": "'"$DESCRIPTION"'",
    "priority": "HIGH",
    "source": "cURL Testing"
  }'

echo ""
echo "Done."
