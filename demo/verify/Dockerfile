# The end-to-end verifier: a headless browser, an MQTT client, a WebSocket client and the Docker API in one image.
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble
RUN pip install --no-cache-dir httpx==0.28.1 websockets==14.1 paho-mqtt==2.1.0 pillow==11.0.0 playwright==1.50.0
WORKDIR /verify
COPY verify.py .
ENTRYPOINT ["python", "-u", "verify.py"]
