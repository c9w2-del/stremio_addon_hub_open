import os
import requests
import feedparser
from flask import Flask, jsonify, request, render_template
from datetime import datetime, timedelta
import json
import re
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- Configuration (from environment variables for security) ---
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TRAKT_CLIENT_ID = os.getenv("TRAKT_CLIENT_ID")
TRAKT_CLIENT_SECRET = os.getenv("TRAKT_CLIENT_SECRET") # Only if you do server-side OAuth
# Add a way to store user-specific Trakt access tokens if implementing user login
# For now, we'll assume public Trakt lists or require user to configure Trakt in Stremio settings


# --- Constants ---
EZTV_RSS_FEED = "https://myrss.org/eztv"
BASE_TMDB_URL = "https://api.themoviedb.org/3"
BASE_TRAKT_URL = "https://api.trakt.tv"

# Cache for API responses (simple in-memory for demonstration)
# In a production environment, use Redis or a more persistent cache
cache = {}
CACHE_TIMEOUT = timedelta(minutes=30) # Cache items for 30 minutes

GENRES_MOVIE = [
    "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary",
    "Drama", "Family", "Fantasy", "History", "Horror", "Music", "Mystery",
    "Romance", "Science Fiction", "TV Movie", "Thriller", "War", "Western"
]

GENRES_TV = [
    "Action & Adventure", "Animation", "Comedy", "Crime", "Documentary",
    "Drama", "Family", "Kids", "Mystery", "News", "Reality",
    "Sci-Fi & Fantasy", "Soap", "Talk", "War & Politics", "Western"
]

GENRES_ANIME = [
    "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Mecha", "Music",
    "Mystery", "Romance", "Sci-Fi", "Slice of Life", "Sports", "Supernatural", "Thriller"
]

# Helper function for caching
def get_cached_response(key, fetch_function):
    now = datetime.now()
    if key in cache and (now - cache[key]['timestamp']) < CACHE_TIMEOUT:
        return cache[key]['data']
    
    data = fetch_function()
    if data:
        cache[key] = {'data': data, 'timestamp': now}
    return data

# --- TMDb Helpers ---
def tmdb_request(endpoint, params=None):
    if not TMDB_API_KEY:
        print("TMDB_API_KEY not set. Please set it in your .env file.")
        return None
    
    url = f"{BASE_TMDB_URL}/{endpoint}"
    full_params = {"api_key": TMDB_API_KEY, "language": "en-US"}
    if params:
        full_params.update(params)
    
    try:
        response = requests.get(url, params=full_params)
        response.raise_for_status() # Raise an exception for HTTP errors
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching from TMDb API ({endpoint}): {e}")
        return None

def get_tmdb_genre_id(genre_name, type_):
    # This assumes a mapping. In a real app, you'd fetch TMDB's genre list once.
    # For simplicity, we'll use a hardcoded mapping or try to guess.
    # It's better to fetch TMDB genres and map them.
    # Example: tmdb_request("genre/movie/list")
    
    # A simplified lookup - for actual use, map the genre names to their IDs.
    # For now, we'll rely on TMDb's 'with_genres' filter expecting IDs.
    # This requires knowing TMDb's genre IDs beforehand, or fetching them.
    
    genre_map = {
        "movie": {
            "Action": 28, "Adventure": 12, "Animation": 16, "Comedy": 35, "Crime": 80,
            "Documentary": 99, "Drama": 18, "Family": 10751, "Fantasy": 14,
            "History": 36, "Horror": 27, "Music": 10402, "Mystery": 9648,
            "Romance": 10749, "Science Fiction": 878, "TV Movie": 10770, "Thriller": 53,
            "War": 10752, "Western": 37
        },
        "tv": { # TMDb TV show genre IDs are different!
            "Action & Adventure": 10759, "Animation": 16, "Comedy": 35, "Crime": 80,
            "Documentary": 99, "Drama": 18, "Family": 10751, "Kids": 10762,
            "Mystery": 9648, "News": 10763, "Reality": 10764, "Sci-Fi & Fantasy": 10765,
            "Soap": 10766, "Talk": 10767, "War & Politics": 10768, "Western": 37
        }
    }
    
    if type_ == "series": # Stremio type "series" maps to TMDb type "tv"
        return genre_map.get("tv", {}).get(genre_name)
    elif type_ == "movie":
        return genre_map.get("movie", {}).get(genre_name)
    return None


def get_meta_from_tmdb(id_type, id_val, media_type):
    """Fetches detailed metadata from TMDb using IMDb ID (or TMDB ID if preferred)."""
    if id_type == "imdb":
        # First, find by IMDb ID
        find_result = tmdb_request(f"find/{id_val}", params={"external_source": "imdb_id"})
        if find_result:
            if media_type == "movie" and find_result.get("movie_results"):
                tmdb_id = find_result["movie_results"][0]["id"]
                data = tmdb_request(f"movie/{tmdb_id}")
            elif media_type == "series" and find_result.get("tv_results"):
                tmdb_id = find_result["tv_results"][0]["id"]
                data = tmdb_request(f"tv/{tmdb_id}")
            else:
                return None
        else:
            return None
    elif id_type == "tmdb": # If you ever pass direct TMDB IDs
        if media_type == "movie":
            data = tmdb_request(f"movie/{id_val}")
        elif media_type == "series":
            data = tmdb_request(f"tv/{id_val}")
        else:
            return None
    else:
        return None

    if not data:
        return None

    poster_path = data.get("poster_path")
    background_path = data.get("backdrop_path")
    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
    background = f"https://image.tmdb.org/t/p/w1280{background_path}" if background_path else None

    if media_type == "movie":
        return {
            "id": f"tt{data['imdb_id']}" if data.get('imdb_id') else f"tmdb:{data['id']}",
            "name": data.get("title"),
            "poster": poster,
            "posterShape": "regular",
            "background": background,
            "description": data.get("overview"),
            "releaseInfo": str(data.get("release_date", "")[:4]),
            "genres": [g["name"] for g in data.get("genres", [])],
            "imdbRating": f"{data.get('vote_average'):.1f}" if data.get('vote_average') else None,
            "type": "movie",
            "trailer": None, # You can add logic to get trailers from TMDb videos
            "runtime": f"{data.get('runtime')} min" if data.get('runtime') else None,
            "director": ", ".join([crew["name"] for crew in data.get("credits", {}).get("crew", []) if crew["job"] == "Director"])
        }
    elif media_type == "series":
        return {
            "id": f"tt{data['external_ids']['imdb_id']}" if data.get('external_ids', {}).get('imdb_id') else f"tmdb:{data['id']}",
            "name": data.get("name"),
            "poster": poster,
            "posterShape": "regular",
            "background": background,
            "description": data.get("overview"),
            "releaseInfo": f"{data.get('first_air_date', '')[:4]} - {data.get('last_air_date', '')[:4] if not data.get('in_production') else ''}",
            "genres": [g["name"] for g in data.get("genres", [])],
            "imdbRating": f"{data.get('vote_average'):.1f}" if data.get('vote_average') else None,
            "type": "series",
            "trailer": None,
            "country": data.get("origin_country")[0] if data.get("origin_country") else None,
            "status": data.get("status"),
            "runtime": f"{data.get('episode_run_time')[0]} min" if data.get('episode_run_time') else None,
            "videos": [], # For episode streams, Stremio will ask for episodes, not a single video.
            "behaviorHints": {
                "has)episodes": True
            },
            "totalSeasons": data.get("number_of_seasons"),
            "totalEpisodes": data.get("number_of_episodes")
        }
    return None

# --- Trakt Helpers ---
def trakt_request(endpoint, params=None):
    if not TRAKT_CLIENT_ID:
        print("TRAKT_CLIENT_ID not set. Trakt features will be limited.")
        return None
    
    url = f"{BASE_TRAKT_URL}/{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": TRAKT_CLIENT_ID
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching from Trakt API ({endpoint}): {e}")
        return None

# --- Addon Endpoints ---

@app.route('/manifest.json')
def manifest():
    with open('manifest.json', 'r') as f:
        return jsonify(json.load(f))

@app.route('/catalog/<type_>/<id_>.json')
@app.route('/catalog/<type_>/<id_>/<extra_args>.json')
def catalog(type_, id_, extra_args=None):
    catalog_id = id_
    extra = {}
    if extra_args:
        # Parse extra_args like "genre=Action&skip=10"
        for param in extra_args.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                extra[key] = value

    genre = extra.get('genre')
    year = extra.get('year')
    skip = int(extra.get('skip', 0))
    page = (skip // 20) + 1 # Assuming 20 items per page for Stremio catalogs

    items = []

    if catalog_id == "latest_tv_shows":
        # Get new shows from Eztv RSS
        # This is a challenging part: mapping EZTV titles to TMDb IDs
        # For simplicity, we'll just parse the feed and try to guess.
        # A more robust solution would involve a dedicated TV show lookup service.
        def fetch_eztv_shows():
            feed = feedparser.parse(EZTV_RSS_FEED)
            entries = []
            for entry in feed.entries:
                title = entry.title
                # Simple regex to extract show name and episode info
                match = re.match(r"^(.*?)(?: Season (\d+) Episode (\d+)| S(\d+)E(\d+))", title, re.IGNORECASE)
                if match:
                    show_name = match.group(1).strip()
                    # Only add if it contains "english" or not explicitly non-english
                    if "english" in title.lower() or not re.search(r'\b(spanish|french|german|italian|russian|korean|japanese)\b', title.lower()):
                         entries.append({"title": show_name, "link": entry.link, "published": entry.published})
            return entries

        eztv_entries = get_cached_response("eztv_latest_shows", fetch_eztv_shows)
        
        processed_shows = set() # To avoid duplicates for the same show
        count = 0
        for entry in eztv_entries:
            if count >= 50 + skip: # Limit to process max 50 entries + skip
                break
            
            show_name = entry["title"]
            if show_name in processed_shows:
                continue
            
            # Attempt to find TMDb ID for the show
            search_results = tmdb_request("search/tv", params={"query": show_name})
            if search_results and search_results.get("results"):
                tmdb_show = search_results["results"][0]
                # Filter by genre if provided
                if genre:
                    tmdb_genre_id = get_tmdb_genre_id(genre, "series")
                    if tmdb_genre_id and tmdb_genre_id not in tmdb_show.get('genre_ids', []):
                        continue # Skip if genre doesn't match
                
                imdb_id = None
                external_ids = tmdb_request(f"tv/{tmdb_show['id']}/external_ids")
                if external_ids and external_ids.get("imdb_id"):
                    imdb_id = external_ids["imdb_id"]
                
                if imdb_id and imdb_id.startswith("tt"):
                    items.append({
                        "id": imdb_id,
                        "type": "series",
                        "name": tmdb_show.get("name"),
                        "poster": f"https://image.tmdb.org/t/p/w500{tmdb_show['poster_path']}" if tmdb_show.get("poster_path") else None,
                        "releaseInfo": tmdb_show.get("first_air_date", "")[:4],
                        "genres": [g["name"] for g in tmdb_show.get("genres", [])] # This won't be in search results direct
                    })
                    processed_shows.add(show_name)
                    count += 1
            if len(items) >= 20: # Stremio usually fetches 100 items per catalog page if not limited
                break
        
    elif catalog_id == "latest_movie_releases":
        params = {"primary_release_date.gte": (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'), # Last 90 days
                  "sort_by": "popularity.desc",
                  "vote_count.gte": 100, # Filter out very obscure items
                  "page": page}
        if year:
            params["primary_release_year"] = year
        if genre:
            tmdb_genre_id = get_tmdb_genre_id(genre, "movie")
            if tmdb_genre_id:
                params["with_genres"] = tmdb_genre_id
        
        movies_data = get_cached_response(f"tmdb_latest_movies_{genre}_{year}_{page}", lambda: tmdb_request("discover/movie", params=params))
        if movies_data and movies_data.get("results"):
            for movie in movies_data["results"]:
                if movie.get("original_language") == "en": # Ensure English content
                    items.append({
                        "id": f"tt{movie['imdb_id']}" if movie.get('imdb_id') else f"tmdb:{movie['id']}",
                        "type": "movie",
                        "name": movie.get("title"),
                        "poster": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get("poster_path") else None,
                        "releaseInfo": movie.get("release_date", "")[:4],
                        "genres": [g["name"] for g in movie.get("genres", [])] # This won't be in search results direct
                    })
        
    elif catalog_id == "latest_dubbed_anime":
        # This is very challenging to accurately filter for "dubbed" from TMDb alone.
        # We'll rely on common anime genres and hope Torrentio finds dubbed streams.
        # You might need to manually curate a list or use an anime-specific API for better results.
        params = {
            "with_genres": get_tmdb_genre_id("Animation", "series"), # Filter by animation genre
            "sort_by": "first_air_date.desc",
            "page": page,
            "with_original_language": "ja" # Japanese original language
        }
        if genre:
            tmdb_genre_id = get_tmdb_genre_id(genre, "tv")
            if tmdb_genre_id:
                params["with_genres"] = f"{get_tmdb_genre_id('Animation', 'series')},{tmdb_genre_id}"
        
        anime_data = get_cached_response(f"tmdb_latest_anime_{genre}_{page}", lambda: tmdb_request("discover/tv", params=params))
        if anime_data and anime_data.get("results"):
            for anime_show in anime_data["results"]:
                # Basic filter: check if it's animation and has some popularity
                if anime_show.get("vote_count", 0) > 100: 
                    items.append({
                        "id": f"tt{anime_show['imdb_id']}" if anime_show.get('imdb_id') else f"tmdb:{anime_show['id']}",
                        "type": "series",
                        "name": f"{anime_show.get('name')} (Dub)", # Indicate it's likely dubbed
                        "poster": f"https://image.tmdb.org/t/p/w500{anime_show['poster_path']}" if anime_show.get("poster_path") else None,
                        "releaseInfo": anime_show.get("first_air_date", "")[:4],
                        "genres": [g["name"] for g in anime_show.get("genres", [])] # This won't be in search results direct
                    })

    elif catalog_id == "top_trending_movies":
        params = {"time_window": "week", "page": page} # Trending this week
        if genre:
            tmdb_genre_id = get_tmdb_genre_id(genre, "movie")
            if tmdb_genre_id:
                params["with_genres"] = tmdb_genre_id
        
        trending_data = get_cached_response(f"tmdb_trending_movies_{genre}_{page}", lambda: tmdb_request("trending/movie/week", params=params))
        if trending_data and trending_data.get("results"):
            for movie in trending_data["results"][:20]: # Limit to top 20
                if movie.get("original_language") == "en":
                    items.append({
                        "id": f"tt{movie['imdb_id']}" if movie.get('imdb_id') else f"tmdb:{movie['id']}",
                        "type": "movie",
                        "name": movie.get("title"),
                        "poster": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get("poster_path") else None,
                        "releaseInfo": movie.get("release_date", "")[:4],
                        "genres": [g["name"] for g in movie.get("genres", [])] # This won't be in search results direct
                    })

    elif catalog_id == "top_trending_tv_shows":
        params = {"time_window": "week", "page": page}
        if genre:
            tmdb_genre_id = get_tmdb_genre_id(genre, "tv")
            if tmdb_genre_id:
                params["with_genres"] = tmdb_genre_id

        trending_data = get_cached_response(f"tmdb_trending_tv_{genre}_{page}", lambda: tmdb_request("trending/tv/week", params=params))
        if trending_data and trending_data.get("results"):
            for tv_show in trending_data["results"][:20]: # Limit to top 20
                if tv_show.get("original_language") == "en":
                    items.append({
                        "id": f"tt{tv_show['imdb_id']}" if tv_show.get('imdb_id') else f"tmdb:{tv_show['id']}",
                        "type": "series",
                        "name": tv_show.get("name"),
                        "poster": f"https://image.tmdb.org/t/p/w500{tv_show['poster_path']}" if tv_show.get("poster_path") else None,
                        "releaseInfo": tv_show.get("first_air_date", "")[:4],
                        "genres": [g["name"] for g in tv_show.get("genres", [])] # This won't be in search results direct
                    })

    elif catalog_id == "recommended_content":
        # This is where Trakt integration would shine for *personalized* recommendations.
        # For a basic implementation without user authentication, we'll recommend highly-rated movies in popular genres.
        params = {
            "sort_by": "vote_average.desc",
            "vote_count.gte": 500, # Only movies with significant votes
            "page": page,
            "with_original_language": "en"
        }
        if genre:
            tmdb_genre_id = get_tmdb_genre_id(genre, "movie")
            if tmdb_genre_id:
                params["with_genres"] = tmdb_genre_id
        
        # Example: Popular movies released recently, highly rated
        recommended_data = get_cached_response(f"tmdb_recommended_movies_{genre}_{page}", lambda: tmdb_request("discover/movie", params=params))
        if recommended_data and recommended_data.get("results"):
            for movie in recommended_data["results"][:20]: # Limit to 20 for this catalog
                items.append({
                    "id": f"tt{movie['imdb_id']}" if movie.get('imdb_id') else f"tmdb:{movie['id']}",
                    "type": "movie",
                    "name": movie.get("title"),
                    "poster": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get("poster_path") else None,
                    "releaseInfo": movie.get("release_date", "")[:4],
                    "genres": [g["name"] for g in movie.get("genres", [])]
                })

    return jsonify({"metas": items})


@app.route('/meta/<type_>/<id_>.json')
def meta(type_, id_):
    # Stremio IDs are typically "ttXXXXXXX" (IMDb ID) or "tvdb:XXXXXX" (TheTVDB ID).
    # We primarily use IMDb IDs for movies/series.
    
    imdb_id = id_
    if id_.startswith("tt"):
        imdb_id = id_
        tmdb_meta = get_meta_from_tmdb("imdb", imdb_id, type_)
    elif id_.startswith("tmdb:"):
        tmdb_id = id_.split(":")[1]
        tmdb_meta = get_meta_from_tmdb("tmdb", tmdb_id, type_)
    else:
        tmdb_meta = None # Handle other ID types if necessary

    if tmdb_meta:
        return jsonify({"meta": tmdb_meta})
    else:
        return jsonify({"meta": None}), 404


@app.route('/stream/<type_>/<id_>.json')
def stream(type_, id_):
    # As discussed, your addon will *not* directly provide torrent streams
    # or Real-Debrid links. You rely on Torrentio for that.
    # Therefore, this endpoint simply returns an empty list of streams.
    # Stremio will then query other installed stream addons (like Torrentio).
    print(f"Stream request for {type_} with ID {id_}. Returning empty streams, relying on Torrentio.")
    return jsonify({"streams": []})

@app.route('/configure')
def configure():
    return render_template('config_page.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=7000)