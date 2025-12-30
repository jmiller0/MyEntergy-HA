FROM python:3.11-slim

# Install system dependencies for Chrome and audio processing
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    ffmpeg \
    xvfb \
    xauth \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome (using modern signed-by method)
RUN wget -q -O /usr/share/keyrings/google-chrome.gpg https://dl-ssl.google.com/linux/linux_signing_key.pub \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY myentergy_auth.py .
COPY RecaptchaSolver.py .
COPY entergy_data_collector.py .
COPY mqtt_publisher.py .

# Create directories for data and cookies
RUN mkdir -p /app/data /app/config

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Entrypoint
ENTRYPOINT ["/docker-entrypoint.sh"]
