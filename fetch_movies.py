#!/usr/bin/env python3
"""
YTS to Real-Debrid Movie Fetcher
Fetches latest movies from YTS API and adds them to Real-Debrid
"""

import os
import sys
import requests
import json
import time
from datetime import datetime
from typing import List, Dict, Optional


class YTSFetcher:
    """Handles fetching movies from YTS API"""
    
    def __init__(self, base_url: str = "https://yts.lt/api/v2"):
        self.base_url = base_url
    
    def get_latest_movies(self, limit: int = 20, minimum_rating: float = 0) -> List[Dict]:
        """
        Fetch latest movies from YTS
        
        Args:
            limit: Number of movies to fetch
            minimum_rating: Minimum IMDB rating (0 for all movies)
        
        Returns:
            List of movie dictionaries with torrent info
        """
        endpoint = f"{self.base_url}/list_movies.json"
        params = {
            "limit": limit,
            "minimum_rating": minimum_rating,
            "sort_by": "date_added",
            "order_by": "desc"
        }
        
        try:
            response = requests.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "ok" and data.get("data", {}).get("movies"):
                return data["data"]["movies"]
            else:
                print("No movies found or API returned error")
                return []
        except requests.exceptions.RequestException as e:
            print(f"Error fetching from YTS: {e}")
            return []


class RealDebridClient:
    """Handles Real-Debrid API interactions"""
    
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.real-debrid.com/rest/1.0"
        self.headers = {
            "Authorization": f"Bearer {api_token}"
        }
    
    def add_magnet(self, magnet_link: str, retry_count: int = 3) -> Optional[str]:
        """
        Add a magnet link to Real-Debrid with retry logic
        
        Args:
            magnet_link: The magnet URI
            retry_count: Number of retries for rate limiting
        
        Returns:
            Torrent ID if successful, None otherwise
        """
        endpoint = f"{self.base_url}/torrents/addMagnet"
        data = {"magnet": magnet_link}
        
        for attempt in range(retry_count):
            try:
                response = requests.post(endpoint, headers=self.headers, 
                                        data=data, timeout=30)
                response.raise_for_status()
                result = response.json()
                return result.get("id")
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limited
                    if attempt < retry_count - 1:
                        wait_time = (attempt + 1) * 5  # Progressive backoff: 5s, 10s, 15s
                        print(f"      Rate limited, waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                print(f"Error adding magnet to Real-Debrid: {e}")
                return None
            except requests.exceptions.RequestException as e:
                print(f"Error adding magnet to Real-Debrid: {e}")
                return None
        
        return None
    
    def select_files(self, torrent_id: str, retry_count: int = 3) -> bool:
        """
        Select all files in a torrent for download with retry logic
        
        Args:
            torrent_id: The torrent ID from Real-Debrid
            retry_count: Number of retries
        
        Returns:
            True if successful, False otherwise
        """
        endpoint = f"{self.base_url}/torrents/selectFiles/{torrent_id}"
        data = {"files": "all"}
        
        for attempt in range(retry_count):
            try:
                response = requests.post(endpoint, headers=self.headers, 
                                        data=data, timeout=30)
                response.raise_for_status()
                return True
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404 and attempt < retry_count - 1:
                    # Torrent might not be ready yet, wait and retry
                    time.sleep(2)
                    continue
                print(f"Error selecting files: {e}")
                return False
            except requests.exceptions.RequestException as e:
                if attempt < retry_count - 1:
                    time.sleep(2)
                    continue
                print(f"Error selecting files: {e}")
                return False
        
        return False
    
    def get_torrents(self, limit: int = 300000) -> List[Dict]:
        """Get list of all torrents (active and completed)"""
        endpoint = f"{self.base_url}/torrents"
        params = {"limit": limit}
        
        try:
            response = requests.get(endpoint, headers=self.headers, 
                                   params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error getting torrents: {e}")
            return []


def create_magnet_link(torrent_hash: str, movie_name: str) -> str:
    """
    Create a magnet link from torrent hash
    
    Args:
        torrent_hash: The torrent hash
        movie_name: Name of the movie for display
    
    Returns:
        Magnet URI string
    """
    # Clean movie name for magnet link
    clean_name = movie_name.replace(" ", "+")
    trackers = [
        "udp://open.demonii.com:1337/announce",
        "udp://tracker.openbittorrent.com:80",
        "udp://tracker.coppersurfer.tk:6969",
        "udp://glotorrents.pw:6969/announce",
        "udp://tracker.opentrackr.org:1337/announce",
        "udp://torrent.gresille.org:80/announce",
        "udp://p4p.arenabg.com:1337",
        "udp://tracker.leechers-paradise.org:6969"
    ]
    
    magnet = f"magnet:?xt=urn:btih:{torrent_hash}&dn={clean_name}"
    for tracker in trackers:
        magnet += f"&tr={tracker}"
    
    return magnet


def main():
    """Main execution function"""
    # Get configuration from environment variables
    rd_api_token = os.getenv("REAL_DEBRID_API_TOKEN")
    max_movies = int(os.getenv("MAX_MOVIES", "10"))
    min_rating = float(os.getenv("MIN_RATING", "0"))
    fetch_all_qualities = os.getenv("FETCH_ALL_QUALITIES", "true").lower() == "true"
    preferred_qualities = ["2160p", "1080p"]  # Order of preference
    
    if not rd_api_token:
        print("ERROR: REAL_DEBRID_API_TOKEN environment variable not set")
        sys.exit(1)
    
    # Check if bulk fetch is complete
    bulk_fetch_complete = os.path.exists("bulk_fetch_complete.flag")
    mode = "incremental" if bulk_fetch_complete else "initial"
    
    print(f"Starting YTS to Real-Debrid sync at {datetime.now().isoformat()}")
    print(f"Mode: {mode.upper()}")
    print(f"Configuration: Max Movies={max_movies}, Min Rating={min_rating}, Fetch All Qualities={fetch_all_qualities}")
    
    # Initialize clients
    yts = YTSFetcher()
    rd = RealDebridClient(rd_api_token)
    
    # Get existing torrents to avoid duplicates
    existing_torrents = rd.get_torrents()
    existing_hashes = {t.get("hash", "").lower() for t in existing_torrents}
    
    print(f"Found {len(existing_hashes)} existing torrents in Real-Debrid")
    
    # Fetch latest movies
    print(f"\nFetching latest movies from YTS...")
    movies = yts.get_latest_movies(limit=max_movies, minimum_rating=min_rating)
    
    if not movies:
        print("No movies found. Exiting.")
        return
    
    print(f"Found {len(movies)} movies\n")
    
    added_count = 0
    skipped_count = 0
    
    # Process each movie
    for movie in movies:
        title = movie.get("title", "Unknown")
        year = movie.get("year", "")
        rating = movie.get("rating", 0)
        torrents = movie.get("torrents", [])
        
        print(f"Processing: {title} ({year}) - Rating: {rating}")
        
        if not torrents:
            print("  No torrents available, skipping")
            skipped_count += 1
            continue
        
        # Process all quality versions if enabled
        if fetch_all_qualities:
            # Get torrents for all preferred qualities
            torrents_to_add = []
            for quality in preferred_qualities:
                for torrent in torrents:
                    if torrent.get("quality") == quality:
                        torrents_to_add.append(torrent)
                        break
        else:
            # Just get the first available torrent
            torrents_to_add = [torrents[0]] if torrents else []
        
        if not torrents_to_add:
            print("  No valid torrents found, skipping")
            skipped_count += 1
            continue
        
        # Add each quality version
        movie_added = False
        for torrent in torrents_to_add:
            torrent_hash = torrent.get("hash", "").lower()
            
            if not torrent_hash:
                print(f"  No valid torrent hash for {torrent.get('quality')}, skipping")
                continue
            
            # Check if already added
            if torrent_hash in existing_hashes:
                print(f"  {torrent.get('quality')} already in Real-Debrid, skipping")
                continue
            
            # Create magnet link and add to Real-Debrid
            magnet = create_magnet_link(torrent_hash, f"{title} {year} {torrent.get('quality')}")
            print(f"  Adding {torrent.get('quality')} ({torrent.get('size')}) to Real-Debrid...")
            
            torrent_id = rd.add_magnet(magnet)
            
            if torrent_id:
                # Small delay to let Real-Debrid process the torrent
                time.sleep(1)
                
                # Select all files for download
                if rd.select_files(torrent_id):
                    print(f"    ✓ Successfully added {torrent.get('quality')} (ID: {torrent_id})")
                    movie_added = True
                    existing_hashes.add(torrent_hash)  # Update local cache
                else:
                    print(f"    ✗ Added but failed to select files")
            else:
                print(f"    ✗ Failed to add to Real-Debrid")
            
            # Rate limiting: wait between requests to avoid hitting API limits
            time.sleep(2)
        
        if movie_added:
            added_count += 1
        else:
            skipped_count += 1
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Movies processed: {len(movies)}")
    print(f"  Added to Real-Debrid: {added_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
