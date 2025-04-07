# Start from Ubuntu:22.04 as the base image (Hackathon Requirement)
FROM ubuntu:22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install Python 3 and pip
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of your application code (including main.py)
COPY . .

# Expose port 8000
EXPOSE 8000

# Command to run your Flask app using python directly
# Assumes your file is main.py and Flask object is app
# The host/port are set in main.py's app.run() call now
CMD ["python3", "main.py"]