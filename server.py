from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import os
import logging
import json
import telebot
from telebot.formatting import escape_markdown
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from typing import Union
import requests
from stt_tools import transcribe_multiple_languages
import uuid
from pydub import AudioSegment
from tts_tools import upload_reference_file, generate_speech
import time

# Initialize FastAPI
app = FastAPI()

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Load config
with open('config.json') as config_file:
    config = json.load(config_file)
    HISTORY_THRESHOLD = config.get('HISTORY_THRESHOLD', 4000)  # Default to 4000 chars if not specified

# Set environment variables for LangSmith
os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGSMITH_API_KEY"] = config["LANGSMITH_API_KEY"]
os.environ["LANGSMITH_PROJECT"] = config["LANGSMITH_PROJECT"]
os.environ["OPENAI_API_KEY"] = config["OPENAI_API_KEY"]

# Configure Telegram bot API endpoints
server_api_uri = 'http://localhost:8081/bot{0}/{1}'
telebot.apihelper.API_URL = server_api_uri
server_file_url = 'http://localhost:8081'
telebot.apihelper.FILE_URL = server_file_url

# Initialize bot from config
with open('config.json') as config_file:
    config = json.load(config_file)
    bot = telebot.TeleBot(config['TOKEN'])
    
# Initialize OpenAI chat model
llm = ChatOpenAI(
    model_name="gpt-4",
    openai_api_key=config['OPENAI_API_KEY']
)

def user_access(message):
    with open('data/users.txt') as f:
        users = f.read().splitlines()
    return str(message['from']['id']) in users

def manage_chat_history(user_id: str, message_id: str, text: Union[str, dict], role: str = "user"):
    """Manages chat history for a user, storing messages and pruning old ones."""
    # Create user directory if it doesn't exist
    user_dir = f'data/users/{user_id}'
    os.makedirs(user_dir, exist_ok=True)

    # Save current message
    date = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'{date}_{message_id}.json'
    
    if isinstance(text, dict):
        # Store directly in new format
        message_data = text
    else:
        # Legacy single message format
        message_data = {
            role: text
        }
    
    with open(os.path.join(user_dir, filename), 'w', encoding='utf-8') as f:
        json.dump(message_data, f, ensure_ascii=False)

    # Get all message files and their creation times
    files = []
    total_length = 0
    for f in os.listdir(user_dir):
        if f.endswith('.json'):
            filepath = os.path.join(user_dir, f)
            with open(filepath, 'r', encoding='utf-8') as file:
                content = json.load(file)
                # Calculate length based on the format of the message
                if 'user' in content and 'assistant' in content:
                    # New format
                    total_length += len(content['user']) + len(content['assistant'])
                elif 'content' in content:
                    # Old format
                    if isinstance(content['content'], dict):
                        total_length += len(content['content']['user_message']) + len(content['content']['assistant_response'])
                    else:
                        total_length += len(content['content'])
                else:
                    # Single message format
                    total_length += sum(len(v) for v in content.values())

    # Sort files by creation time (oldest first)
    files.sort(key=lambda x: x[1])

    # Remove oldest files until total length is below threshold
    while total_length > HISTORY_THRESHOLD and files:
        filepath, _, content = files[0]
        total_length -= len(content['content'])
        os.remove(filepath)
        files.pop(0)

def get_chat_history(user_id: str) -> list:
    """Retrieves chat history for a user as a list of message tuples,
    including any initialization history."""
    # First, get any initialization history
    init_data = get_user_init_data(user_id)
    history = []
    
    # Add initialization history if it exists
    if 'chat_history' in init_data and isinstance(init_data['chat_history'], list):
        for entry in init_data['chat_history']:
            if isinstance(entry, list) and len(entry) == 2:
                history.append((entry[0], entry[1]))
    
    user_dir = f'data/users/{user_id}'
    if not os.path.exists(user_dir):
        return history  # Return just initialization history if no user directory

    # Get all message files and their creation times
    files = []
    for f in os.listdir(user_dir):
        if f.endswith('.json') and f != 'init_config.json':
            filepath = os.path.join(user_dir, f)
            files.append((filepath, os.path.getctime(filepath)))

    # Sort files by creation time (oldest first)
    files.sort(key=lambda x: x[1])

    # Add regular chat history
    for filepath, _ in files:
        with open(filepath, 'r', encoding='utf-8') as f:
            message_data = json.load(f)
            if 'user' in message_data and 'assistant' in message_data:
                # Handle new format
                history.extend([
                    ("user", message_data['user']),
                    ("assistant", message_data['assistant'])
                ])
            elif isinstance(message_data.get('content'), dict):
                # Handle old conversation format
                content = message_data['content']
                history.extend([
                    ("user", content['user_message']),
                    ("assistant", content['assistant_response'])
                ])
            else:
                # Handle legacy single message format
                history.append((message_data['role'], message_data['content']))

    return history

def clear_chat_history(user_id: str) -> None:
    """Clears all chat history for a given user."""
    user_dir = f'data/users/{user_id}'
    if os.path.exists(user_dir):
        for file in os.listdir(user_dir):
            # Skip the init_config.json file which contains mentagram configuration
            if file.endswith('.json') and file != 'init_config.json':
                os.remove(os.path.join(user_dir, file))

def convert_audio_to_wav(input_path: str) -> str:
    """
    Convert audio file to WAV format with 16kHz sample rate, mono channel, and 16-bit depth.
    Returns path to converted file and temp directory.
    """
    # Create unique output directory
    output_dir = f'data/{str(uuid.uuid4())}'
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate output path
    output_path = os.path.join(output_dir, 'audio.wav')
    
    # Convert audio with explicit parameters
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_frame_rate(16000)  # Set sample rate to 16kHz
    audio = audio.set_channels(1)        # Convert to mono
    audio = audio.set_sample_width(2)    # Set to 16-bit (2 bytes)
    
    # Export with explicit parameters
    audio.export(
        output_path,
        format="wav",
        parameters=["-acodec", "pcm_s16le"]  # Force 16-bit PCM encoding
    )
    
    return output_path, output_dir

def send_voice_message(chat_id, voice_file_path, reply_to_message_id=None):
    """Helper function to send voice messages via Telegram"""
    try:
        # Convert WAV to OGG format with OPUS codec
        audio = AudioSegment.from_wav(voice_file_path)
        ogg_path = voice_file_path.replace('.wav', '.ogg')
        audio.export(
            ogg_path,
            format="ogg",
            codec="libopus",  # Ensure we're using OPUS codec
            parameters=["-strict", "-2"]  # Required for some ffmpeg versions
        )
        
        # Send the OGG file using file object
        with open(ogg_path, 'rb') as voice_file:
            logger.info(f"Sending voice message: {ogg_path}")
            bot.send_voice(
                chat_id,
                voice_file,  # Send the file object instead of path
                reply_to_message_id=reply_to_message_id
            )
            
        # Clean up OGG file
        os.remove(ogg_path)
            
    except Exception as e:
        logger.error(f"Error sending voice message: {e}")
        if 'VOICE_MESSAGES_FORBIDDEN' in str(e):
            bot.send_message(
                chat_id,
                "Sorry, I can't send voice messages. Please enable voice messages for everyone in your Telegram privacy settings (Settings -> Privacy and Security -> Voice Messages).",
                reply_to_message_id=reply_to_message_id
            )
        raise

def process_llm_response(user_id: str, message_id: str, user_message: str, chat_id: int, reply_to_message_id: int, language: str = 'en') -> None:
    """Common function to handle LLM processing and response generation"""
    try:
        # Language format simplification "en-US" -> "en"
        language = language.split('-')[0]
                
        # Get chat history and create prompt template
        chat_history = get_chat_history(user_id)
        
        # Get initialization data for custom system prompt
        init_data = get_user_init_data(user_id)
        system_prompt = init_data.get('system_prompt', 
            f"Your name is Janet. You are a helpful AI assistant. Please respond in {language} language.")
        
        # Create prompt template with history placeholder
        history_placeholder = MessagesPlaceholder("history")
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            history_placeholder,
            ("human", "{question}")
        ])

        # Generate prompt with chat history
        prompt_value = prompt_template.invoke({
            "history": chat_history,
            "question": user_message
        })

        # Get response from LLM
        llm_response = llm.invoke(prompt_value).content

        # Store both user message and LLM response
        manage_chat_history(
            user_id,
            str(message_id),
            {
                "user": user_message,
                "assistant": llm_response
            }
        )
        # Replace dots with newlines in the LLM response
        llm_response = llm_response.replace('.', '\n')
        # Crop extra spaces and newlines
        llm_response = llm_response.strip()

        # Generate and send voice response
        try:
            # Get TTS server URL from config
            tts_api_url = config.get('TTS_API_URL', 'http://localhost:5000')
            
            # Generate speech using the user's reference file
            speech_file_name = generate_speech(
                text=llm_response,
                language=language,
                reference_file=f"{user_id}.wav",
                api_url=tts_api_url
            )
            
            # Send voice message
            send_voice_message(
                chat_id,
                speech_file_name,
                reply_to_message_id=reply_to_message_id
            )
            
            # Clean up
            os.remove(speech_file_name)
            
        except Exception as e:
            logger.error(f"Error generating or sending voice message: {e}")
            # Fall back to text message if voice generation fails
            bot.send_message(
                chat_id,
                llm_response,
                reply_to_message_id=reply_to_message_id,
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error in LLM processing: {e}")
        bot.send_message(
            chat_id,
            "Sorry, there was an error processing your message.",
            reply_to_message_id=reply_to_message_id
        )

async def send_reply(bot_token, chat_id, message_id, text):
    url = f"http://localhost:8081/bot{bot_token}/sendMessage"
    # Escape dots in text for MarkdownV2 format
    text = text.replace('.', '\\.')
    payload = {
        'chat_id': chat_id,
        'text': f"*{text}*",
        'reply_to_message_id': message_id,
        'parse_mode': 'MarkdownV2'
    }
    response = requests.post(url, data=payload)
    logger.info(f"Update message response: {response.json()}")
    return response.json()

@app.post("/message")
async def call_message(request: Request, authorization: str = Header(None)):
    message = await request.json()
    logger.info(message)

    # if not user_access(message):
    #     return JSONResponse(content={
    #         "type": "text", 
    #         "body": "You are not authorized to use this bot."
    #     })

    chat_id = message['chat']['id']
    user_id = str(message['from']['id'])

    # Handle document uploads
    if 'document' in message and 'mime_type' in message['document']:
        # Handle mentagram.json file
        if message['document']['file_name'] == 'mentagram.json' and 'application/json' in message['document']['mime_type']:
            try:
                # Get the file from Telegram
                file_id = message['document']['file_id']
                file_info = bot.get_file(file_id)
                file_path = file_info.file_path
                
                # Load and parse the mentagram.json file
                with open(file_path, 'r') as f:
                    init_data = json.load(f)
                
                # Save the initialization data
                save_user_init_data(user_id, init_data)
                
                bot.send_message(
                    chat_id,
                    "Initialization file successfully processed!",
                    reply_to_message_id=message['message_id']
                )
            except Exception as e:
                logger.error(f"Error processing mentagram.json file: {e}")
                bot.send_message(
                    chat_id,
                    "Sorry, there was an error processing the initialization file.",
                    reply_to_message_id=message['message_id']
                )
            return JSONResponse(content={"type": "empty", "body": ''})
        
        # Handle audio documents (existing code)
        elif 'audio' in message['document']['mime_type']:
            # Existing code for audio document processing...
            pass

    # Handle voice message
    if 'voice' in message and 'audio' in message['voice']['mime_type']:
        voice_file_id = message['voice']['file_id']
        duration = message['voice']['duration']
        
        if duration < 1:
            response = "Voice message received, but duration is too short < 1 sec."
        elif duration > 60:
            response = "Voice message received, but duration is too long: > 60 sec."
        else:
            # Send status message
            # bot.send_message(
            #     chat_id,
            #     "Converting audio...",
            #     reply_to_message_id=message['message_id']
            # )
            update_message = await send_reply(config['TOKEN'], chat_id, message['message_id'], "[     ] Reading the reference voice..")
            update_id = update_message['result']['message_id']
            # Get the file path using the Telegram API
            file_info = bot.get_file(voice_file_id)
            file_path = file_info.file_path
            # Log file info and path
            logger.info(f"File info: {file_info}")
            logger.info(f"File path: {file_path}")
            # Check if file exists at file_path
            if not os.path.exists(file_path):
                logger.error(f"File not found at path: {file_path}")
                bot.send_message(
                    chat_id,
                    "Sorry, there was an error accessing the voice message file.",
                    reply_to_message_id=message['message_id']
                )
                return JSONResponse(content={"type": "empty", "body": ''})
            
            # Convert audio to WAV format
            try:
                start_time = time.time()
                bot.edit_message_text(
                    "`[█    ] Voice convertation..`".replace('.', '\\.'),
                    chat_id=chat_id,
                    message_id=update_id,
                    parse_mode='MarkdownV2'
                )
                wav_path, temp_dir = convert_audio_to_wav(file_path)
                logger.info(f"WAV path: {wav_path}")
                logger.info(f"Temp dir: {temp_dir}")
                
                with open("BCP-47.txt", "r") as f:
                    languages = [line.strip() for line in f if line.strip()]
                
                bot.edit_message_text(
                    "`[██   ] Voice to text transcribation..`".replace('.', '\\.'),
                    chat_id=chat_id,
                    message_id=update_id,
                    parse_mode='MarkdownV2'
                )
                stt_response = transcribe_multiple_languages(wav_path, languages)
                for result in stt_response.results:
                    detected_language = result.language_code
                    transcript = result.alternatives[0].transcript
                    logger.info(f"Detected Language: {detected_language}")
                    logger.info(f"Transcript: {transcript}")
                    
                    # Get chat history and create prompt template
                    chat_history = get_chat_history(user_id)
                    
                    # Create prompt template with history placeholder
                    history_placeholder = MessagesPlaceholder("history")
                    prompt_template = ChatPromptTemplate.from_messages([
                        ("system", "Your name is Janet. You are a helpful AI assistant."),
                        history_placeholder,
                        ("human", "{question}")
                    ])

                    # Generate prompt with chat history
                    prompt_value = prompt_template.invoke({
                        "history": chat_history,
                        "question": transcript
                    })

                    # Replace Chinese language code for compatibility
                    if detected_language.lower() == "cmn-hans-cn":
                        detected_language = "zh-cn"
                    
                    bot.edit_message_text(
                        f"`[███  ] [{detected_language}] Thinking..`".replace('.', '\\.'),
                        chat_id=chat_id,
                        message_id=update_id,
                        parse_mode='MarkdownV2'
                    )
                    
                    # Get response from LLM
                    llm_response = llm.invoke(prompt_value).content

                    # Store both transcribed message and LLM response
                    manage_chat_history(
                        user_id,
                        str(message['message_id']),
                        {
                            "user": transcript,
                            "assistant": llm_response
                        }
                    )

                    bot.edit_message_text(
                        f"`[████ ] [{detected_language}] Voice synthesis..`".replace('.', '\\.'),
                        chat_id=chat_id,
                        message_id=update_id,
                        parse_mode='MarkdownV2'
                    )
                    
                    # Process LLM response
                    process_llm_response(
                        user_id,
                        message['message_id'],
                        transcript,
                        chat_id,
                        message['message_id'],
                        detected_language
                    )
                    logger.info(f"Voice response sent to user {user_id}")
                    bot.edit_message_text(
                        f"`[█████] [{detected_language}] Done in {round(time.time() - start_time, 1)} sec.`".replace('.', '\\.'),
                        chat_id=chat_id,
                        message_id=update_id,
                        parse_mode='MarkdownV2'
                    )
                # Clean up temporary files
                os.remove(wav_path)
                os.rmdir(temp_dir)
                return JSONResponse(content={"type": "empty", "body": ''})
                
            except Exception as e:
                logger.error(f"Error processing audio: {e}")
                response = "Sorry, there was an error processing the voice message."
                bot.send_message(
                    chat_id,
                    response,
                    reply_to_message_id=message['message_id']
                )

        return JSONResponse(content={"type": "empty", "body": ''})

    # Original text message handling
    if 'text' not in message:
        bot.send_message(
            chat_id,
            "Sorry, this message type is not supported yet.",
            reply_to_message_id=message['message_id']
        )
        return JSONResponse(content={"type": "empty", "body": ''})

    text = message['text']

    if text == '/reset':
        clear_chat_history(user_id)
        bot.send_message(
            chat_id,
            "Chat history has been reset.",
            reply_to_message_id=message['message_id']
        )
        return JSONResponse(content={"type": "empty", "body": ''})
    
    if text == '/start':
        try:
            with open('greeting.txt', 'r') as f:
                greeting = f.read()
            with open("BCP-47.txt", "r") as f:
                languages = [line.strip() for line in f if line.strip()]
            greeting += f'\nSupported languages: {languages}'
            greeting += "\n\nUse /mentagram to get your personalization file. You can edit this file and upload it back to customize how I behave and respond to you!"
            
            # Send voclone.png with caption
            try:
                with open('voclone.png', 'rb') as photo:
                    bot.send_photo(
                        chat_id,
                        photo,
                        caption=greeting,
                        reply_to_message_id=message['message_id']
                    )
            except FileNotFoundError:
                # Fall back to text if image not available
                bot.send_message(
                    chat_id,
                    greeting,
                    reply_to_message_id=message['message_id']
                )
            return JSONResponse(content={"type": "empty", "body": ''})
        except FileNotFoundError:
            logger.error("greeting.txt not found")
            bot.send_message(
                chat_id,
                "Welcome! I'm Janet, your AI assistant. You can use /mentagram to customize how I behave!",
                reply_to_message_id=message['message_id']
            )
            return JSONResponse(content={"type": "empty", "body": ''})

    # Handle the /mind command to provide a sample or current mentagram.json
    if text == '/mentagram':
        # Log the /mentagram command
        logger.info(f"User {user_id} requested mentagram configuration")
        # Get current init data or create sample if none exists
        init_data = get_user_init_data(user_id)
        
        # If user has no init data, load from mentagram.json
        if not init_data:
            try:
                with open('mentagram.json', 'r', encoding='utf-8') as f:
                    init_data = json.load(f)
            except FileNotFoundError:
                logger.error("mentagram.json not found")
                init_data = {
                    "system_prompt": "Your name is Janet. You are a helpful AI assistant that specializes in answering questions clearly and accurately.",
                    "chat_history": [
                        ["system", "Remember to be friendly and concise in your responses."],
                        ["user", "What can you help me with?"],
                        ["assistant", "I can help you with information, answering questions, creative writing, language translation, and more. Just let me know what you need!"]
                    ]
                }
        
        # Create temporary file to send to user
        temp_file_path = f'data/init_{user_id}.json'
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            json.dump(init_data, f, ensure_ascii=False, indent=2)
        
        # Send file to user
        with open(temp_file_path, 'rb') as f:
            bot.send_document(
                chat_id,
                f,
                caption="Here's your current mentagram configuration. You can modify this file and upload it back to change how I behave.",
                reply_to_message_id=message['message_id'],
                visible_file_name="mentagram.json"
            )
        
        # Clean up temp file
        os.remove(temp_file_path)
        return JSONResponse(content={"type": "empty", "body": ''})

    # Process LLM response
    process_llm_response(
        user_id,
        message['message_id'],
        text,
        chat_id,
        message['message_id'],
        'en'
    )

    return JSONResponse(content={"type": "empty", "body": ''})

@app.get("/test")
async def call_test():
    return JSONResponse(content={"status": "ok"})

def save_user_init_data(user_id: str, init_data: dict) -> None:
    """Saves user initialization data from mentagramjson"""
    user_dir = f'data/users/{user_id}'
    os.makedirs(user_dir, exist_ok=True)
    
    # Save the initialization data
    init_file_path = os.path.join(user_dir, 'init_config.json')
    with open(init_file_path, 'w', encoding='utf-8') as f:
        json.dump(init_data, f, ensure_ascii=False)
    
    logger.info(f"Initialization data saved for user {user_id}")

def get_user_init_data(user_id: str) -> dict:
    """Retrieves user initialization data if it exists"""
    init_file_path = f'data/users/{user_id}/init_config.json'
    if os.path.exists(init_file_path):
        with open(init_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def reset_user_init_data(user_id: str) -> None:
    """Removes the initialization data for a user"""
    init_file_path = f'data/users/{user_id}/init_config.json'
    if os.path.exists(init_file_path):
        os.remove(init_file_path)
        logger.info(f"Initialization data reset for user {user_id}")