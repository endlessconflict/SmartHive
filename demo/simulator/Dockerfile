# Five simulated hive nodes. Build context: the repository root (see docker-compose.yml).
FROM python:3.11-slim
RUN pip install --no-cache-dir paho-mqtt==2.1.0 onnxruntime==1.20.1 numpy==2.2.1 opencv-python-headless==4.10.0.84
WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
COPY edge/raspberry/pi_node ./pi_node
COPY demo/simulator/model ./model
COPY demo/simulator/corpus /corpus
COPY demo/simulator/detector.py demo/simulator/sim.py ./
COPY demo/simulator/demo-ctl /usr/local/bin/demo-ctl
RUN sed -i 's/\r$//' /usr/local/bin/demo-ctl && chmod +x /usr/local/bin/demo-ctl
EXPOSE 8090
CMD ["python", "sim.py"]
