FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Install dependencies if any exist
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt || true

# Copy application source code
COPY . /app/

# Render provides $PORT dynamically
EXPOSE 8080

CMD ["python", "-u", "server.py"]
