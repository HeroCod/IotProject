FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY collector.py .
COPY entrypoint.sh .

# Copy ML model parameters
RUN mkdir -p ./ml
COPY ../ml/train_params.json ./ml/train_params.json

RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["sh", "entrypoint.sh"]