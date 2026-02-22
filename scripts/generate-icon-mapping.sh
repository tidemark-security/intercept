#!/bin/bash
# Generate icon mapping from Lucide React icons
# Maps icon names to Lucide React components

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_FILE="$PROJECT_ROOT/frontend/src/utils/iconMapping.tsx"
ICONS_DIR="$PROJECT_ROOT/frontend/node_modules/lucide-react/dist/esm/icons"

echo "🎨 Generating icon mapping from Lucide React icons..."

# Check if the icons directory exists
if [ ! -d "$ICONS_DIR" ]; then
    echo "❌ Error: Lucide icons directory not found at $ICONS_DIR"
    echo "   Please run 'npm install' in the frontend directory first."
    exit 1
fi

# Dynamically discover all Lucide icons from node_modules
# Convert kebab-case filenames to PascalCase component names
# e.g., arrow-down.js -> ArrowDown
ICONS=()
for file in "$ICONS_DIR"/*.js; do
    # Skip .map files and index.js
    [[ "$file" == *.map ]] && continue
    [[ "$(basename "$file")" == "index.js" ]] && continue
    
    # Get the basename without extension
    filename=$(basename "$file" .js)
    
    # Convert kebab-case to PascalCase
    # e.g., arrow-down -> ArrowDown, check-circle-2 -> CheckCircle2
    pascal_name=$(echo "$filename" | sed -E 's/(^|-)([a-z0-9])/\U\2/g')
    
    ICONS+=("$pascal_name")
done

# Sort the icons array for consistent output
IFS=$'\n' ICONS=($(sort -u <<<"${ICONS[*]}")); unset IFS

echo "📦 Found ${#ICONS[@]} Lucide icons"

# Start the file
cat > "$OUTPUT_FILE" << 'EOF'
/**
 * Icon Mapping Utility
 * 
 * Maps string icon names from the database to React components.
 * This allows the backend to store icon identifiers as strings
 * while the frontend renders the actual Lucide React components.
 * 
 * AUTO-GENERATED - DO NOT EDIT MANUALLY
 * Run: scripts/generate-icon-mapping.sh
 */

import React from 'react';
import {
EOF

# Generate imports
for icon in "${ICONS[@]}"; do
    echo "  $icon," >> "$OUTPUT_FILE"
done

echo "} from 'lucide-react';" >> "$OUTPUT_FILE"
echo "import { MSTeamsIcon, VirusTotalIcon } from '@/assets';" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Generate the icon map
cat >> "$OUTPUT_FILE" << 'EOF'
/**
 * Map of icon names to React components
 */
export const ICON_MAP: Record<string, React.ReactNode> = {
EOF

# Add all icons to the map
# Using size="1em" so icons inherit font-size from parent
for icon in "${ICONS[@]}"; do
    echo "  $icon: <$icon size=\"1em\" />," >> "$OUTPUT_FILE"
done

# Add custom icons (these already have width/height="1em" in their SVG)
echo "  MSTeamsIcon: <MSTeamsIcon />," >> "$OUTPUT_FILE"
echo "  VirusTotalIcon: <VirusTotalIcon />," >> "$OUTPUT_FILE"

cat >> "$OUTPUT_FILE" << 'EOF'
};

/**
 * Get a React icon component from a string name
 * 
 * @param iconName - String identifier for the icon (e.g., 'Mail')
 * @returns React component or null if not found
 */
export function getIconComponent(iconName: string): React.ReactNode {
  return ICON_MAP[iconName] || null;
}

/**
 * Get all available icon names
 * 
 * @returns Array of all registered icon names
 */
export function getAvailableIconNames(): string[] {
  return Object.keys(ICON_MAP);
}
EOF

echo "✅ Generated icon mapping with ${#ICONS[@]} Lucide icons"
echo "📄 Output: $OUTPUT_FILE"
