FROM python:3.9.16
WORKDIR /server

# Install FFmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /server
RUN pip3 install -r requirements.txt --no-cache-dir
COPY api.json /server
ENV GOOGLE_APPLICATION_CREDENTIALS="/server/api.json"
COPY stt_tools.py /server
COPY tts_tools.py /server
COPY BCP-47.txt /server
COPY greeting.txt /server
COPY mentagram.json /server
COPY server.py /server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "4223"]