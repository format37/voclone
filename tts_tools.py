import requests
import os
import time
import uuid
import logging

logger = logging.getLogger(__name__)
# Set logger level to INFO
logger.setLevel(logging.INFO)

def generate_speech(text, language, reference_file='asmr_0.wav', api_url="http://localhost:5000"):
    # Request payload
    payload = {
        'text': text,
        'language': language,
        'reference_file': reference_file
    }
    
    try:
        # Send POST request
        response = requests.post(f"{api_url}/tts", json=payload)
        logger.info(f"TTS response: {response}")
        # Check if request was successful
        if response.status_code == 200:
            # Create data directory if it doesn't exist
            os.makedirs('data', exist_ok=True)
            
            # Generate unique filename using UUID
            unique_id = str(uuid.uuid4())
            output_filename = f'data/speech_{unique_id}.wav'
            
            # Save the audio file
            with open(output_filename, 'wb') as f:
                f.write(response.content)
            print(f"Audio saved as {output_filename}")
            return output_filename
        else:
            print(f"Error: {response.json().get('error', 'Unknown error')}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Connection error: {str(e)}")
        return None

def upload_reference_file(file_path, api_url="http://localhost:5000", filename="reference.wav"):
    """
    Upload a reference audio file to the TTS server
    
    Args:
        file_path (str): Path to the audio file
        api_url (str): Base URL of the API server
    
    Returns:
        dict: Server response
    """
    # Check if file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Prepare the file and filename for upload
    files = {
        'file': open(file_path, 'rb')
    }
    
    data = {
        'filename': filename
    }
    
    try:
        response = requests.post(
            f"{api_url}/upload_reference",
            files=files,
            data=data
        )
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.RequestException as e:
        print(f"Error uploading file: {str(e)}")
        raise
    finally:
        files['file'].close()

if __name__ == "__main__":
    url = 'https://d676-5-178-149-227.ngrok-free.app'
    # Example Russian text
    text = "Так, кажется кому-то пора помыть посуду"
    language = 'ru'
    reference_file = 'kompot.wav'
    # Generate speech
    generate_speech(url, text, language, reference_file)
