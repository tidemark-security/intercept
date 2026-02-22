#!/bin/bash
# Check for Lucide icons used without size prop inside IconWrapper
# This helps catch potential icon sizing issues

set -e

echo "🔍 Checking for Lucide icons without size prop..."

# Find files that import from lucide-react and use IconWrapper
# This is a simple heuristic check, not a full AST analysis

FRONTEND_SRC="/home/gb/projects/intercept/frontend/src"

# Look for patterns like <SomeIcon /> or <SomeIcon className= without size=
# inside files that use IconWrapper

warnings=0

# Check for icon usages in IconWrapper that don't have size prop
# Pattern: <IconWrapper...><SomeIcon /></IconWrapper> without size="1em"
while IFS= read -r -d '' file; do
    # Skip node_modules and generated files
    if [[ "$file" == *"node_modules"* ]] || [[ "$file" == *"iconMapping.tsx"* ]]; then
        continue
    fi
    
    # Check if file uses IconWrapper
    if grep -q "IconWrapper" "$file" 2>/dev/null; then
        # Look for lucide icons without size prop (basic heuristic)
        # This looks for patterns like <Activity /> or <Activity className= but not <Activity size=
        matches=$(grep -n "<[A-Z][a-zA-Z]*\s*/>" "$file" 2>/dev/null | grep -v "size=" || true)
        if [ -n "$matches" ]; then
            echo ""
            echo "⚠️  Potential issue in $file:"
            echo "$matches"
            ((warnings++)) || true
        fi
    fi
done < <(find "$FRONTEND_SRC" -name "*.tsx" -print0)

echo ""
if [ $warnings -gt 0 ]; then
    echo "⚠️  Found $warnings file(s) with potential icon sizing issues"
    echo "   Icons inside IconWrapper should use size=\"1em\" to inherit font-size"
    echo ""
    echo "   Example fix:"
    echo "   - <Activity />"
    echo "   + <Activity size=\"1em\" />"
    exit 0  # Don't fail the build, just warn
else
    echo "✅ No obvious icon sizing issues found"
fi
