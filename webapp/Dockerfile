FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY templates/ ./templates/

# Create static directory (optional)
RUN mkdir -p ./static

# Expose webapp port
EXPOSE 5000

CMD ["python", "app.py"]
