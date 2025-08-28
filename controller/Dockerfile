FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY controller.py .

# Create ML directory (will be mounted as volume at runtime)
RUN mkdir -p ml

# Install netcat for health checks
RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*

# Expose REST API port
EXPOSE 5001

CMD ["python", "controller.py"]