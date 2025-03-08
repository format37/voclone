#!/bin/bash

# Script to build and run the bot server container
# Should be placed in the project root directory

# Set the container name
CONTAINER_NAME="voclonebot"
IMAGE_NAME="voclonebot_image"

echo "Starting bot server deployment..."

# Check if the container is already running
if [ "$(sudo docker ps -q -f name=$CONTAINER_NAME)" ]; then
    echo "Container is already running. Stopping and removing..."
    sudo docker stop $CONTAINER_NAME
    sudo docker rm $CONTAINER_NAME
fi

# Check if the container exists but is stopped
if [ "$(sudo docker ps -aq -f status=exited -f name=$CONTAINER_NAME)" ]; then
    echo "Removing stopped container..."
    sudo docker rm $CONTAINER_NAME
fi

# Build the Docker image
echo "Building Docker image..."
sudo docker build -t $IMAGE_NAME .

# Check if build was successful
if [ $? -eq 0 ]; then
    echo "Docker image built successfully."
else
    echo "Error building Docker image. Exiting..."
    exit 1
fi