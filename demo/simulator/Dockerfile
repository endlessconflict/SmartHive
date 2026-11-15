# Five simulated hive nodes. Build context: the repository root (see docker-compose.yml).
FROM python:3.11-slim
RUN pip install --no-cache-dir paho-mqtt==2.1.0
# SmartHive-Vision v0.5.0, the release pinned in vision.lock: the same runtime the Raspberry Pi runs
COPY demo/simulator/vision/smarthive_vision-0.5.0-py3-none-any.whl /tmp/
RUN pip install --no-cache-dir /tmp/smarthive_vision-0.5.0-py3-none-any.whl && rm /tmp/*.whl
WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
COPY edge/raspberry/pi_node ./pi_node
COPY demo/simulator/vision/models /models/v0.5
COPY demo/simulator/corpus /corpus
COPY demo/simulator/sim.py ./sim.py
COPY demo/simulator/demo-ctl /usr/local/bin/demo-ctl
RUN sed -i 's/\r$//' /usr/local/bin/demo-ctl && chmod +x /usr/local/bin/demo-ctl
EXPOSE 8090
CMD ["python", "sim.py"]
