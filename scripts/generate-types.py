#!/usr/bin/env python3
"""
TypeScript Type Generation Script

This script generates TypeScript types from the FastAPI backend's OpenAPI specification.
It should be run from the project root directory.

Usage:
    python scripts/generate-types.py
"""

import os
import sys
import json
import subprocess
import logging
from pathlib import Path

# Add the backend directory to Python path to import the FastAPI app
project_root = Path(__file__).parent.parent
backend_path = project_root / "backend"
sys.path.insert(0, str(backend_path))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_dependencies():
    """Check if required dependencies are installed."""
    logger.info("Checking dependencies...")
    
    # Check if openapi-typescript-codegen is installed in frontend
    frontend_path = project_root / "frontend"
    
    # Check package.json for the dependency
    package_json_path = frontend_path / "package.json"
    if package_json_path.exists():
        import json
        with open(package_json_path, 'r') as f:
            package_data = json.load(f)
        
        dev_deps = package_data.get('devDependencies', {})
        if 'openapi-typescript-codegen' not in dev_deps:
            logger.info("openapi-typescript-codegen not found in package.json. Installing...")
            try:
                subprocess.run(
                    ["npm", "install", "--save-dev", "openapi-typescript-codegen"],
                    cwd=frontend_path,
                    check=True,
                    capture_output=True,
                    text=True
                )
                logger.info("Successfully installed openapi-typescript-codegen")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to install openapi-typescript-codegen: {e}")
                logger.error(f"stderr: {e.stderr}")
                return False
    
    return True


def generate_openapi_spec():
    """Generate OpenAPI specification from FastAPI app."""
    logger.info("Generating OpenAPI specification...")
    
    try:
        # Import the FastAPI app
        from app.main import app
        
        # Generate OpenAPI specification
        openapi_spec = app.openapi()
        
        # Ensure the temp directory exists
        temp_dir = project_root / "temp"
        temp_dir.mkdir(exist_ok=True)
        
        # Write OpenAPI spec to file
        spec_file = temp_dir / "openapi.json"
        with open(spec_file, "w") as f:
            json.dump(openapi_spec, f, indent=2)
        
        logger.info(f"OpenAPI specification saved to {spec_file}")
        return spec_file
        
    except Exception as e:
        logger.error(f"Failed to generate OpenAPI specification: {e}")
        logger.error(f"Make sure the backend dependencies are installed and the app can be imported")
        return None


def generate_typescript_types(spec_file):
    """Generate TypeScript types using openapi-typescript-codegen."""
    logger.info("Generating TypeScript types...")
    
    frontend_path = project_root / "frontend"
    output_dir = frontend_path / "src" / "types" / "generated"
    
    # Remove existing generated types
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
        logger.info("Removed existing generated types")
    
    try:
        # Run openapi-typescript-codegen with enhanced options
        cmd = [
            "npx", "openapi-typescript-codegen",
            "--input", str(spec_file),
            "--output", str(output_dir),
            "--client", "axios",
            "--useUnionTypes",
            "--useOptions",
            "--exportCore", "true",
            "--exportServices", "true",
            "--exportModels", "true",
            "--exportSchemas", "false"
        ]
        
        result = subprocess.run(
            cmd,
            cwd=frontend_path,
            check=True,
            capture_output=True,
            text=True
        )
        
        logger.info(f"TypeScript types generated successfully in {output_dir}")
        logger.info("Generation output:")
        logger.info(result.stdout)
        
        # Post-process for camelCase conversion
        if not process_typescript_files(output_dir):
            logger.warning("Post-processing failed, but types were generated")
        
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to generate TypeScript types: {e}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        return False


def update_frontend_types():
    """Update the main types file to re-export generated types."""
    logger.info("Updating frontend types...")
    
    types_index_file = project_root / "frontend" / "src" / "types" / "index.ts"
    generated_types_exist = (project_root / "frontend" / "src" / "types" / "generated").exists()
    
    if generated_types_exist:
        # Read current content
        try:
            with open(types_index_file, "r") as f:
                content = f.read()
            
            # Add export for generated types if not already present
            export_line = "export * from './generated';"
            if export_line not in content:
                content = f"{export_line}\n\n{content}"
                
                with open(types_index_file, "w") as f:
                    f.write(content)
                
                logger.info("Added export for generated types to index.ts")
            else:
                logger.info("Generated types export already exists in index.ts")
                
        except Exception as e:
            logger.error(f"Failed to update types index file: {e}")


def cleanup():
    """Clean up temporary files."""
    logger.info("Cleaning up temporary files...")
    
    temp_dir = project_root / "temp"
    if temp_dir.exists():
        import shutil
        shutil.rmtree(temp_dir)
        logger.info("Temporary files cleaned up")


def snake_to_camel(snake_str):
    """Convert snake_case to camelCase."""
    components = snake_str.split('_')
    return components[0] + ''.join(word.capitalize() for word in components[1:])


def process_typescript_files(output_dir):
    """Post-process TypeScript files - no conversion needed, use snake_case as-is."""
    logger.info("Post-processing TypeScript files - keeping snake_case naming...")
    
    try:
        # No field name conversions needed - using snake_case throughout
        # Just log that we're keeping the original naming
        for ts_file in output_dir.rglob("*.ts"):
            logger.info(f"Processed {ts_file} - kept original snake_case naming")
        
        logger.info("Completed post-processing - using snake_case throughout")
        return True
        
    except Exception as e:
        logger.error(f"Error during post-processing: {e}")
        return False


def create_api_mapper():
    """No API field mapping needed - using snake_case throughout."""
    logger.info("Skipping API field mapper - using snake_case throughout...")
    
    # No field mapping utilities needed since we're using snake_case consistently
    logger.info("No field mapping utilities created - snake_case used throughout")
    return True


def main():
    """Main function to orchestrate type generation."""
    logger.info("Starting TypeScript type generation from FastAPI OpenAPI spec...")
    logger.info(f"Project root: {project_root}")
    
    try:
        # Change to project root directory
        os.chdir(project_root)
        
        # Check dependencies
        if not check_dependencies():
            sys.exit(1)
        
        # Generate OpenAPI specification
        spec_file = generate_openapi_spec()
        if not spec_file:
            sys.exit(1)
        
        # Generate TypeScript types
        if not generate_typescript_types(spec_file):
            sys.exit(1)
        
        # Update frontend types
        update_frontend_types()
        
        # Post-process TypeScript files (no conversion needed)
        output_dir = project_root / "frontend" / "src" / "types" / "generated"
        process_typescript_files(output_dir)
        
        # No API field mapper needed for snake_case approach
        create_api_mapper()
        
        # Cleanup
        cleanup()
        
        logger.info("✅ TypeScript types generated successfully!")
        logger.info("Generated types are available in frontend/src/types/generated/")
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
