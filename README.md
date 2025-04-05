# Subdomain Finder Web Application

A Flask web application for finding subdomains and checking live hosts, based on the functionality of the original bash script. This version includes multithreading optimizations for faster scanning.

## Features

- Find subdomains using multiple sources:
  - subfinder (with 50 threads)
  - crt.sh
  - AlienVault OTX
- Check which subdomains are live using httpx (with 100 threads)
- Collect historical URLs using gau (with 50 threads)
- Scan for open ports using naabu (top 100 ports)
- Color-coded HTTP status codes (2xx green, 3xx blue, 4xx red)
- On-demand GAU scanning via buttons next to each live host
- On-demand port scanning via buttons next to each live host
- Real-time progress updates with Server-Sent Events
- Progress bar and live counters during scanning
- Clean web interface to display results
- Filter and search through results

## Requirements

- Python 3.7+
- Flask
- Requests
- External tools (optional but recommended):
  - [subfinder](https://github.com/projectdiscovery/subfinder)
  - [httpx](https://github.com/projectdiscovery/httpx)
  - [gau](https://github.com/lc/gau)
  - [naabu](https://github.com/projectdiscovery/naabu)

## Installation

### Option 1: Using Docker (Recommended)

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/subdomain-finder.git
   cd subdomain-finder
   ```

2. Build and run with Docker Compose:
   ```
   docker-compose up -d
   ```

3. Access the application at:
   ```
   http://localhost:5001
   ```

### Option 2: Manual Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/subdomain-finder.git
   cd subdomain-finder
   ```

2. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Install external tools (required for full functionality):

   **subfinder**:
   ```
   GO111MODULE=on go get -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder
   ```

   **httpx**:
   ```
   GO111MODULE=on go get -v github.com/projectdiscovery/httpx/cmd/httpx
   ```

   **gau**:
   ```
   GO111MODULE=on go get -v github.com/lc/gau
   ```

   **naabu**:
   ```
   GO111MODULE=on go get -v github.com/projectdiscovery/naabu/v2/cmd/naabu
   ```

## Usage

1. If using manual installation, start the Flask application:
   ```
   python app.py
   ```

2. Open your web browser and navigate to:
   ```
   http://localhost:5001
   ```

   The application is also accessible from other devices on your network using your computer's IP address:
   ```
   http://YOUR_IP_ADDRESS:5001
   ```

3. Enter a domain name (e.g., example.com) and click "Scan"

4. View the results in the web interface

## Notes

- The application will check if the required external tools are installed
- If tools are missing, the application will still work but with limited functionality:
  - Without subfinder: Only crt.sh will be used for subdomain enumeration
  - Without httpx: Live host checking will be skipped
  - Without gau: Historical URL collection will be skipped
  - Without naabu: Port scanning will be skipped

## Docker

The Docker setup includes:

- All required tools pre-installed (subfinder, httpx, gau, naabu)
- Volume mapping for persistent output storage
- Exposed port 5001 for web access

### Docker Build Approach

The Dockerfile uses pre-built binaries for all tools instead of compiling from source. This approach:

- Makes the build process faster and more reliable
- Uses specific tested versions of each tool
- Reduces the image size
- Avoids compilation issues

### Docker Commands

**Build and run with Docker Compose (recommended):**
```
docker-compose up -d
```

**Build the Docker image manually:**
```
docker build -t reconaug .
```

**Run the container manually:**
```
docker run -d -p 5001:5001 -v $(pwd)/output:/app/output --name reconaug reconaug
```

**Stop the container:**
```
docker stop reconaug
```

**Remove the container:**
```
docker rm reconaug
```

**View logs:**
```
docker logs -f reconaug
```

**Rebuild the container (after changes):**
```
docker-compose up -d --build
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
