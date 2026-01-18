# parser/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (needed for some python C-extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python deps (including the large spacy model)
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .
CMD ["python", "parse_document.py"]