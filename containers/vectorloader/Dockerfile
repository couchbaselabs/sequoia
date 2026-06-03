FROM --platform=linux/amd64 python:3.10-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir couchbase>=4.0.0

# Create embeddings directory (mount point for large files)
RUN mkdir -p /app/embeddings

# Copy the vectorloader script
COPY vectorloader.py /app/vectorloader.py

# Set entrypoint
ENTRYPOINT ["python3", "/app/vectorloader.py"]
