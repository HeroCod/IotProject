FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY collector.py .
COPY entrypoint.sh .

RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["sh", "entrypoint.sh"]