FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl procps openjdk-21-jre docker.io && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir fastapi==0.115.0 uvicorn[standard]==0.30.6 redis==5.2.1 pyspark==3.5.3

COPY src /app/src
COPY scripts /app/scripts

ENV PYTHONPATH=/app/src
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
