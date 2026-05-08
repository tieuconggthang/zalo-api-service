#!/bin/bash
# Build Docker image for Zalo API Service

echo "=========================================="
echo "🔨 Building Zalo API Service Docker Image"
echo "=========================================="

# Check if docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker first."
    exit 1
fi

# Build
echo "Building image: zalo-api-service:latest..."
docker build -t zalo-api-service:latest .

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Build successful!"
    echo ""
    echo "To run the container:"
    echo "  docker-compose up -d"
    echo ""
    echo "Or manually:"
    echo "  docker run -d -p 10000:10000 -v ./data:/app/data zalo-api-service:latest"
else
    echo ""
    echo "❌ Build failed!"
    exit 1
fi
