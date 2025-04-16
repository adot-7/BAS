The renders which can be added, but at the cost of latency:

![Screenshot 2025-04-07 214611](https://github.com/user-attachments/assets/85086d73-8309-4b0a-90bc-79506d73bf1b)
![Screenshot 2025-04-07 214603](https://github.com/user-attachments/assets/2ab2f737-c4e0-41a6-9ade-1a7aac27576b)
![Screenshot 2025-04-07 214545](https://github.com/user-attachments/assets/b65e262f-a7e7-4c77-8c5d-1467fc9ac9d3)


## How to Run (Using Docker)

This project is designed to be run inside a Docker container, following the Hackathon requirements.

**Prerequisites:**

*   **Git:** Must be installed to clone the repository.
*   **Docker:** Must be installed and running on your system. ([Install Docker](https://docs.docker.com/get-docker/))

**Steps:**

1.  **Clone the Repository:**
    Open your terminal or command prompt and clone the repository:
    ```bash
    git clone https://github.com/adot-7/BAS.git
    cd BAS
    ```

2.  **Build the Docker Image:**
    Navigate into the cloned `BAS` directory (if you aren't already there) where the `Dockerfile` is located and run:
    ```bash
    docker build -t bas-stowage-app .
    ```
    *(You can replace `bas-stowage-app` with any image name you prefer)*

3.  **Run the Docker Container:**
    Start the container using the following command:
    ```bash
    docker run -d -p 8000:8000 -it bas-stowage-app
    ```
    *   `-p 8000:8000`: Maps port 8000 on your host machine to port 8000 inside the container.
    *   `-it`: Runs the container interactively, allowing you to see logs and stop it with `CTRL+C`.

4.  **Access the Application:**
    Once the container shows that the application is running (e.g., Flask server started), open your web browser and navigate to:
    ```
    http://localhost:8000
    ```
    You should see the application's front-end or be able to interact with the API endpoints at this address.

**To Stop the Application:**

*   Press `CTRL+C` in the terminal where the `docker run` command is active.
