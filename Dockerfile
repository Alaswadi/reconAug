FROM golang:1.20 AS go-builder

# Install build dependencies
RUN apt-get update && apt-get install -y git build-essential libpcap-dev

# Set up Go environment
ENV GO111MODULE=on
ENV CGO_ENABLED=1

# Create a temporary directory for Go modules
WORKDIR /go/src/tools

# Install subfinder
RUN go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest

# Install httpx
RUN go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest

# Install gau
RUN go install -v github.com/lc/gau/v2/cmd/gau@latest

# Install naabu (requires CGO for pcap)
RUN go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest

FROM python:3.9-slim

# Copy Go binaries from go-builder
COPY --from=go-builder /go/bin/subfinder /usr/local/bin/
COPY --from=go-builder /go/bin/httpx /usr/local/bin/
COPY --from=go-builder /go/bin/gau /usr/local/bin/
COPY --from=go-builder /go/bin/naabu /usr/local/bin/

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    nmap \
    libpcap-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create config directories for tools
RUN mkdir -p /root/.config/subfinder \
    && mkdir -p /root/.config/httpx \
    && mkdir -p /root/.config/naabu

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
