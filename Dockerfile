# Start from Ubuntu:22.04 as the base image (Hard Requirement)
FROM ubuntu:22.04

# Set environment variables to avoid interactive prompts and ensure logs appear
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Update package lists and install Python 3, pip, and build essentials
# Clean up apt cache afterwards to keep the image smaller
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip python3-dev build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first to leverage Docker cache
# Assumes you have a requirements.txt listing Flask, pandas, etc.
# Make sure py3dbp is NOT in requirements.txt if you're copying the source code
COPY requirements.txt .

# Install Python dependencies from requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy ALL your project code into the container's working directory (/app)
# This includes app.py, static/, templates/, AND your local py3dbp/ directory
COPY . .

# Expose port 8000 (Hard Requirement)
EXPOSE 8000

# Define the command to run your Flask application
# Ensure app.py runs on host='0.0.0.0' to be accessible from outside the container
CMD ["python3", "app.py"]