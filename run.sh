# Set the container name
CONTAINER_NAME="echobridgebot"
IMAGE_NAME="echobridgebot_image"
TELEGRAM_BOT_TOKEN="your_bot_token"

# Check if config.json exists
if [ ! -f "$(pwd)/config.json" ]; then
    echo "Error: config.json not found in the current directory"
    exit 1
fi

# Create data directory if it doesn't exist
if [ ! -d "$(pwd)/data" ]; then
    echo "Creating data directory..."
    mkdir -p "$(pwd)/data"
fi

# Run the container
echo "Starting container..."
sudo docker run -d \
    --name $CONTAINER_NAME \
    --network host \
    --restart unless-stopped \
    -v "$(pwd)/data:/server/data" \
    -v "$(pwd)/config.json:/server/config.json" \
    --mount type=bind,source="/$TELEGRAM_BOT_TOKEN",target="/$TELEGRAM_BOT_TOKEN" \
    -v /etc/localtime:/etc/localtime:ro \
    -v /etc/timezone:/etc/timezone:ro \
    $IMAGE_NAME

# Check if container started successfully
if [ "$(sudo docker ps -q -f name=$CONTAINER_NAME)" ]; then
    echo "Container started successfully!"
    echo "Bot server is running on port 4222"
else
    echo "Error: Container failed to start."
    exit 1
fi