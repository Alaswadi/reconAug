FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    nmap \
    libpcap-dev \
    ca-certificates \
    git \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install Sublist3r
RUN git clone https://github.com/aboul3la/Sublist3r.git /tools/Sublist3r \
    && cd /tools/Sublist3r \
    && pip install -r requirements.txt

# Create directories
RUN mkdir -p /tools /app/output /root/.config/subfinder /root/.config/httpx /root/.config/naabu

# Set up Chaos API key for subfinder
RUN mkdir -p /root/.config/subfinder
RUN echo '{"chaos_api_key": "47a628d5-3721-4ae6-8369-a1111e509cfb"}' > /root/.config/subfinder/config.yaml

# Install subfinder
RUN wget -q https://github.com/projectdiscovery/subfinder/releases/download/v2.6.3/subfinder_2.6.3_linux_amd64.zip -O /tmp/subfinder.zip \
    && unzip /tmp/subfinder.zip -d /tmp \
    && mv /tmp/subfinder /usr/local/bin/ \
    && chmod +x /usr/local/bin/subfinder \
    && rm /tmp/subfinder.zip

# Install httpx
RUN wget -q https://github.com/projectdiscovery/httpx/releases/download/v1.3.7/httpx_1.3.7_linux_amd64.zip -O /tmp/httpx.zip \
    && unzip /tmp/httpx.zip -d /tmp \
    && mv /tmp/httpx /usr/local/bin/ \
    && chmod +x /usr/local/bin/httpx \
    && rm /tmp/httpx.zip

# Install naabu
RUN wget -q https://github.com/projectdiscovery/naabu/releases/download/v2.1.8/naabu_2.1.8_linux_amd64.zip -O /tmp/naabu.zip \
    && unzip /tmp/naabu.zip -d /tmp \
    && mv /tmp/naabu /usr/local/bin/ \
    && chmod +x /usr/local/bin/naabu \
    && rm /tmp/naabu.zip

# Install gau
RUN wget -q https://github.com/lc/gau/releases/download/v2.1.2/gau_2.1.2_linux_amd64.tar.gz -O /tmp/gau.tar.gz \
    && tar -xzf /tmp/gau.tar.gz -C /tmp \
    && mv /tmp/gau /usr/local/bin/ \
    && chmod +x /usr/local/bin/gau \
    && rm /tmp/gau.tar.gz

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create output directory
RUN mkdir -p output

# Expose port
EXPOSE 5001

# Run the application
CMD ["python", "app.py"]
