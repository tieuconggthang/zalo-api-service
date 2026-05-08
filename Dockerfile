FROM ubuntu:24.04

# Install Node.js 22 and Python
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    git \
    python3 \
    python3-pip \
    python3-venv \
    python3-full \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install openzca globally
RUN npm install -g openzca

# Copy Node.js dependencies cho zca-js (QR login)
COPY zalo_plugin/package*.json ./zalo_plugin/
RUN cd zalo_plugin && npm install

# Copy Python requirements
COPY requirements.txt .
RUN pip3 install --break-system-packages --no-cache-dir -r requirements.txt

# Copy all source code
COPY . .

# Copy startup script
COPY startup.sh .
RUN chmod +x startup.sh

# Create data directory
RUN mkdir -p /app/data

# Environment
ENV PYTHONUNBUFFERED=1
ENV NODE_NO_WARNINGS=1
ENV HERMES_HOME=/app/data
ENV ZALO_SESSION=/app/data/zalo_session.json
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:10000/health || exit 1

CMD ["./startup.sh"]
