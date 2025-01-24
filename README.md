# EchoBridgeBot

A sophisticated AI-powered voice cloning and conversation system that enables natural, personalized interactions through voice synthesis and recognition.

## Overview

(EchoBridgeBot)[https://t.me/voclonebot] facilitates meaningful conversations with AI using voice cloning technology. Whether conducting practice interviews or engaging in personal interactions, the system provides an authentic and emotionally resonant experience through personalized voice synthesis.

## Key Features

- **Simple Voice Cloning**: Instant voice adaptation through WAV file upload
- **Multi-language Support**: Automatic language detection and processing
- **Real-time Processing**: Fast response times through distributed architecture
- **Secure Communication**: Protected data transmission via ngrok tunneling

## Technical Stack

- **Voice Synthesis**: Custom TTS implementation with GPU acceleration
- **Speech Recognition**: Google Cloud Speech-to-Text API
- **API Gateway**: FastAPI for microservice communication
- **Proxy Service**: ngrok for secure tunneling
- **Bot Framework**: Custom Telegram server for rapid response handling
- **Containerization**: Docker-based microservices architecture

## Installation

1. Clone the repository:
```bash
git clone https://github.com/format37/echobridgebot.git
cd echobridgebot
```

2. Configure the environment:
   - Set up `config.json` with required API keys and settings
   - Configure Telegram bot settings
   - Set up ngrok for TTS service access

3. Build and deploy services:
```bash
cd bot_server
chmod +x build.sh run.sh logs.sh
sh build_and_run.sh
```

## Configuration

1. Create and configure `config.json`:
```json
{
    "TOKEN": "your_telegram_token",
    "OPENAI_API_KEY": "your_openai_key",
    "LANGSMITH_API_KEY": "your_langsmith_key",
    "LANGSMITH_PROJECT": "echobridgebot",
    "HISTORY_THRESHOLD": 4000,
    "TTS_API_URL": "http://localhost:5000"
}
```

2. Set up ngrok for TTS service:
```bash
sudo snap install ngrok
```

Configure ngrok service:
```yaml
version: "3"
agent:
    authtoken: your_token
endpoints:
  - name: tts-tunnel
    url: your_url
    upstream:
      url: 5000
```

## Usage

1. Start a conversation with the bot on Telegram
2. Upload a WAV file as voice reference
3. Send voice messages to interact with the AI
4. Use `/reset` to clear conversation history

## Dependencies

- Python 3.9+
- FastAPI
- Google Cloud Speech-to-Text
- PyTelegramBotAPI
- LangChain
- FFmpeg
- Docker

## Related Projects

- [TTS Repository](https://github.com/format37/tts/tree/main/TTS)
- [Telegram Bot Framework](https://github.com/format37/telegram_bot)

## License

This project is licensed under the MIT License - see the LICENSE file for details.