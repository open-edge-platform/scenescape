#!/bin/bash

# 3D Mapping Models API - Quick Start Script
# This script helps you quickly build and run the mapping models API service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_usage() {
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  build       Build the Docker container"
    echo "  api         Start the API service"
    echo "  test        Test the API with example images"
    echo "  health      Check API health"
    echo "  logs        Show live service logs"
    echo "  stop        Stop all services"
    echo "  clean       Clean up containers and images"
    echo ""
    echo "Options:"
    echo "  --gpu       Enable GPU support (requires nvidia-docker)"
    echo "  --help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 build"
    echo "  $0 api --gpu"
    echo "  $0 test"
    echo "  $0 health"
    echo "  $0 logs"
    echo "  $0 test-logs"
}

check_dependencies() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed${NC}"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        echo -e "${RED}Error: Docker Compose is not installed${NC}"
        exit 1
    fi
}

build_container() {
    echo -e "${BLUE}Building 3D Mapping Models container...${NC}"
    
    # Use docker compose v2 if available, otherwise fallback to docker-compose
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi
    
    $DOCKER_COMPOSE build mapping-models-api
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Container built successfully!${NC}"
    else
        echo -e "${RED}❌ Container build failed!${NC}"
        exit 1
    fi
}

start_api() {
    local gpu_flag=""
    
    if [[ "$*" == *"--gpu"* ]]; then
        echo -e "${YELLOW}Enabling GPU support...${NC}"
        gpu_flag="--profile gpu"
        
        # Check if nvidia-docker is available
        if ! docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi &> /dev/null; then
            echo -e "${RED}Warning: GPU support requested but nvidia-docker may not be properly configured${NC}"
        fi
    fi
    
    echo -e "${BLUE}Starting API service...${NC}"
    
    # Use docker compose v2 if available
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi
    
    $DOCKER_COMPOSE up -d $gpu_flag mapping-models-api
    
    echo -e "${GREEN}✅ API service started!${NC}"
    echo -e "${BLUE}API will be available at: http://localhost:8000${NC}"
    echo -e "${BLUE}Health check at: http://localhost:8000/health${NC}"
    echo -e "${YELLOW}Note: Initial startup may take several minutes for model downloads${NC}"
    echo ""
    echo "You can check the startup progress with:"
    echo "  $0 logs"
}



test_api() {
    echo -e "${BLUE}Testing API with example images...${NC}"
    
    # Check if API is running
    if ! curl -s http://localhost:8000/health > /dev/null; then
        echo -e "${RED}❌ API is not running. Please start it first with: $0 api${NC}"
        exit 1
    fi
    
    # Check if we have example images
    if [ -f "input_images/qcam1.jpg" ] && [ -f "input_images/qcam2.jpg" ]; then
        echo -e "${GREEN}Using example images...${NC}"
        python3 client_example.py --images input_images/qcam1.jpg input_images/qcam2.jpg --model mapanything --output test_reconstruction.glb
    else
        echo -e "${YELLOW}Example images not found. Testing health check only...${NC}"
        python3 client_example.py --health-check
    fi
}

check_health() {
    echo -e "${BLUE}Checking API health...${NC}"
    
    if ! curl -s http://localhost:8000/health > /dev/null; then
        echo -e "${RED}❌ API is not accessible at http://localhost:8000${NC}"
        echo "Make sure the API service is running with: $0 api"
        exit 1
    fi
    
    python3 client_example.py --health-check
}

show_logs() {
    # Use docker compose v2 if available
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi
    
    echo -e "${BLUE}Showing service logs...${NC}"
    echo -e "${YELLOW}Press Ctrl+C to exit log viewer${NC}"
    echo ""
    $DOCKER_COMPOSE logs -f mapping-models-api
}

stop_services() {
    echo -e "${BLUE}Stopping services...${NC}"
    
    # Use docker compose v2 if available
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi
    
    $DOCKER_COMPOSE down
    echo -e "${GREEN}✅ Services stopped!${NC}"
}

clean_up() {
    echo -e "${BLUE}Cleaning up containers and images...${NC}"
    
    # Use docker compose v2 if available
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi
    
    $DOCKER_COMPOSE down --rmi all --volumes
    echo -e "${GREEN}✅ Cleanup completed!${NC}"
}

# Main script
if [ $# -eq 0 ]; then
    print_usage
    exit 0
fi

check_dependencies

case "$1" in
    "build")
        build_container
        ;;
    "api")
        start_api "$@"
        ;;
    "test")
        test_api
        ;;
    "health")
        check_health
        ;;
    "logs")
        show_logs
        ;;
    "stop")
        stop_services
        ;;
    "clean")
        clean_up
        ;;
    "--help"|"help")
        print_usage
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        print_usage
        exit 1
        ;;
esac