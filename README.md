# Your Awesome Entertainment Hub Stremio Addon

This is a self-hosted Stremio addon providing curated catalogs of English-released TV shows, movies, and anime. It leverages TMDb for metadata and trending lists, EZTV RSS for new TV shows, and is designed to work seamlessly with the Torrentio addon (with Real-Debrid configured) for stream resolution.

## Features

* **Latest TV Shows (EN):** Fetches recent TV show releases from EZTV, attempts to map them to TMDb for rich metadata, and filters for English content.
* **Latest Movie Releases (EN):** Lists newly released movies, primarily sourced from TMDb.
* **Latest Dubbed Anime (EN):** Attempts to list recently released anime that are likely to have English dubbed versions.
* **Top 20 Movies Trending:** Shows the top 20 trending English movies.
* **Top 20 TV Shows Trending:** Shows the top 20 trending English TV shows.
* **Recommended For You (Movies):** Provides a simple recommendation list based on highly-rated popular movies.
* **Genre & Year Filtering:** Most catalogs support filtering by genre and year (for movies).
* **Integrates with Torrentio + Real-Debrid:** This addon provides *metadata*. For actual streams, you must have the **Torrentio** addon installed in Stremio and configured with your **Real-Debrid** account. This addon will *not* provide direct torrent or Real-Debrid links itself.

## Setup & Self-Hosting on Debian 12

### Prerequisites

* Debian 12 server
* Python 3.x and `pip`
* `git`
* Nginx (for reverse proxy)
* Gunicorn (Python WSGI HTTP Server)
* A TMDb API Key (get one from [TMDb](https://www.themoviedb.org/documentation/api/terms-of-use))
* A Trakt API Key (optional, for advanced recommendations - get one from [Trakt API](https://trakt.tv/oauth/applications))

### Installation Steps

1.  **Update your system:**
    ```bash
    sudo apt update && sudo apt upgrade -y
    ```

2.  **Install Python, pip, and Git:**
    ```bash
    sudo apt install python3 python3-pip git -y
    ```

3.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/stremio-addon-hub.git](https://github.com/your-username/stremio-addon-hub.git) # Replace with your repo URL
    cd stremio-addon-hub
    ```

4.  **Create a Python Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

5.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

6.  **Configure Environment Variables:**
    Create a `.env` file in the `stremio_addon_hub` directory:
    ```bash
    cp .env.example .env
    ```
    Edit the `.env` file and add your TMDb and Trakt API keys:
    ```
    TMDB_API_KEY=your_actual_tmdb_api_key
    TRAKT_CLIENT_ID=your_actual_trakt_client_id
    TRAKT_CLIENT_SECRET=your_actual_trakt_client_secret
    ```
    **Important:** Keep your `.env` file secure and do not commit it to public Git repositories.

7.  **Test the Flask application (optional):**
    ```bash
    python3 app.py
    ```
    You should see output indicating it's running on `http://0.0.0.0:7000`. Test by visiting `http://your_server_ip:7000/manifest.json` in your browser. Press `Ctrl+C` to stop.

8.  **Install Gunicorn:**
    Gunicorn is a production-ready WSGI HTTP server.
    ```bash
    pip install gunicorn
    ```

9.  **Create a Systemd Service File:**
    This will ensure your addon starts automatically on boot.
    Create a file: `/etc/systemd/system/stremio-addon-hub.service`
    ```bash
    sudo nano /etc/systemd/system/stremio-addon-hub.service
    ```
    Add the following content (replace `your_username` and `/path/to/stremio-addon-hub`):
    ```ini
    [Unit]
    Description=Stremio Addon Hub Service
    After=network.target

    [Service]
    User=your_username
    WorkingDirectory=/path/to/stremio-addon-hub
    ExecStart=/path/to/stremio-addon-hub/venv/bin/gunicorn -w 4 app:app -b 127.0.0.1:7000
    Restart=always
    EnvironmentFile=/path/to/stremio-addon-hub/.env # Load environment variables

    [Install]
    WantedBy=multi-user.target
    ```
    Save and exit (`Ctrl+X`, `Y`, `Enter`).

10. **Enable and Start the Service:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable stremio-addon-hub
    sudo systemctl start stremio-addon-hub
    ```
    Check its status: `sudo systemctl status stremio-addon-hub`

11. **Install and Configure Nginx (Reverse Proxy):**
    ```bash
    sudo apt install nginx -y
    ```
    Create an Nginx configuration file: `/etc/nginx/sites-available/stremio-addon-hub`
    ```bash
    sudo nano /etc/nginx/sites-available/stremio-addon-hub
    ```
    Add the following content (replace `your-domain.com` or `your_server_ip`):
    ```nginx
    server {
        listen 80;
        server_name your-domain.com your_server_ip; # Use your domain or IP address

        location / {
            proxy_pass [http://127.0.0.1:7000](http://127.0.0.1:7000); # Forward requests to your Flask app
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_cache_bypass $http_upgrade;
        }
    }
    ```
    Save and exit.

12. **Enable the Nginx site and test:**
    ```bash
    sudo ln -s /etc/nginx/sites-available/stremio-addon-hub /etc/nginx/sites-enabled/
    sudo nginx -t
    sudo systemctl reload nginx
    ```

13. **Configure Firewall (UFW):**
    ```bash
    sudo ufw allow 'Nginx HTTP'
    sudo ufw enable
    ```
    Confirm status: `sudo ufw status`

## Adding to Stremio

Once your addon is running and accessible via `http://your-server-ip/manifest.json` (or your domain), open Stremio:

1.  Go to **Addons**.
2.  Click on **My Addons** (or the puzzle piece icon).
3.  Scroll down to "Install an Addon from URL".
4.  Enter the URL to your addon's `manifest.json`: `http://your-server-ip/manifest.json` (or your domain).
5.  Click "Install".

## Important Notes

* **API Keys:** Never hardcode your API keys directly in `app.py`. Use environment variables as shown (`.env` file).
* **Dubbed Anime:** Accurately identifying "dubbed only" anime from general APIs like TMDb is challenging. The current implementation relies on genre filters and hoping for dubbed streams via Torrentio. For better accuracy, a dedicated anime API with specific dub status might be needed.
* **Caching:** The caching implemented is a simple in-memory cache. For larger deployments, consider using Redis or a dedicated caching solution.
* **Stream Resolution:** This addon provides *metadata and catalog listings only*. It does **not** provide direct streaming links. You **must** have **Torrentio** (with **Real-Debrid** configured) installed in Stremio for streams to appear.
* **Trakt Integration:** The Trakt integration is currently minimal (client ID only). To offer personalized recommendations, you'd need to implement OAuth for user authentication, which is more complex and involves a redirect URL.

---