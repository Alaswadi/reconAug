#!/bin/bash

# This script switches to the alternative Dockerfile that uses pre-built binaries
# instead of compiling from source

echo "Switching to alternative Dockerfile that uses pre-built binaries..."
mv Dockerfile Dockerfile.src
mv Dockerfile.alt Dockerfile
echo "Done! You can now build the Docker image with: docker-compose build"
