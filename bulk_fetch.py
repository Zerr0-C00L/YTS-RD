#!/usr/bin/env python3
"""
YTS to Real-Debrid Bulk Fetcher
Fetches ALL movies from YTS API and adds them to Real-Debrid
This is a one-time bulk operation - run manually or once via GitHub Actions
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
    
    def get_total_movie_count(self) -> int:
        """Get total number of movies in YTS database"""
        endpoint = f"{self.base_url}/list_movies.json"
        params = {"limit": 1}
        
        try:
            response = requests.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "ok":
                return data.get("data", {}).get("movie_count", 0)
            return 0
        except requests.exceptions.RequestException as e:
            print(f"Error getting movie count: {e}")
            return 0
    
    def get_movies_page(self, page: int = 1, limit: int = 50, 
                       minimum_rating: float = 0) -> tuple[List[Dict], int]:
        """
        Fetch a page of movies from YTS
        
        Args:
            page: Page number (1-indexed)
            limit: Number of movies per page (max 50)
            minimum_rating: Minimum IMDB rating (0 for all movies)
        
        Returns:
            Tuple of (list of movies, total page count)
        """
        endpoint = f"{self.base_url}/list_movies.json"
        params = {
            "limit": min(limit, 50),  # API max is 50
            "page": page,
            "minimum_rating": minimum_rating,
            "sort_by": "date_added",
            "order_by": "desc"
        }
        
        try:
            response = requests.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "ok" and data.get("data", {}).get("movies"):
                movies = data["data"]["movies"]
                movie_count = data["data"].get("movie_count", 0)
                limit = data["data"].get("limit", 50)
                page_count = (movie_count + limit - 1) // limit  # Ceiling division
                return movies, page_count
            else:
                return [], 0
        except requests.exceptions.RequestException as e:
            print(f"Error fetching page {page} from YTS: {e}")
            return [], 0


class RealDebridClient:
    """Handles Real-Debrid API interactions"""
    
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.real-debrid.com/rest/1.0"
        self.headers = {
            "Authorization": f"Bearer {api_token}"
        }
    
    def add_magnet(self, magnet_link: str, retry_count: int = 3) -> Optional[str]:
        """Add a magnet link to Real-Debrid with retry logic"""
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
                        wait_time = (attempt + 1) * 10  # Progressive backoff
                        print(f"      Rate limited, waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                return None
            except requests.exceptions.RequestException:
                return None
        
        return None
    
    def select_files(self, torrent_id: str, retry_count: int = 3) -> bool:
        """Select all files in a torrent for download with retry logic"""
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
                    time.sleep(2)
                    continue
                return False
            except requests.exceptions.RequestException:
                if attempt < retry_count - 1:
                    time.sleep(2)
                    continue
                return False
        
        return False
    
    def get_torrents(self, limit: int = 100000) -> List[Dict]:
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
    """Create a magnet link from torrent hash"""
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
    min_rating = float(os.getenv("MIN_RATING", "0"))
    start_page = int(os.getenv("START_PAGE", "1"))
    max_pages = int(os.getenv("MAX_PAGES", "0"))  # 0 = all pages
    batch_size = int(os.getenv("BATCH_SIZE", "500"))  # Process in batches to avoid crashes
    preferred_qualities = ["2160p", "1080p"]
    
    if not rd_api_token:
        print("ERROR: REAL_DEBRID_API_TOKEN environment variable not set")
        sys.exit(1)
    
    print("="*70)
    print("YTS TO REAL-DEBRID BULK FETCHER")
    print("="*70)
    print(f"Started at: {datetime.now().isoformat()}")
    print(f"Configuration:")
    print(f"  - Minimum Rating: {min_rating}")
    print(f"  - Starting Page: {start_page}")
    print(f"  - Max Pages: {'All' if max_pages == 0 else max_pages}")
    print(f"  - Batch Size: {batch_size} pages (to prevent crashes)")
    print(f"  - Qualities: {', '.join(preferred_qualities)} (2160p, 1080p only)")
    print("="*70)
    
    # Initialize clients
    yts = YTSFetcher()
    rd = RealDebridClient(rd_api_token)
    
    # Get total movie count
    print("\nFetching total movie count from YTS...")
    total_movies = yts.get_total_movie_count()
    print(f"Total movies in YTS database: {total_movies:,}")
    
    # Get existing torrents to avoid duplicates
    print("Fetching existing torrents from Real-Debrid...")
    existing_torrents = rd.get_torrents()
    existing_hashes = {t.get("hash", "").lower() for t in existing_torrents}
    print(f"Found {len(existing_hashes):,} existing torrents in Real-Debrid")
    
    # Statistics
    total_added = 0
    total_skipped = 0
    total_failed = 0
    movies_processed = 0
    
    # Fetch first page to get page count
    print(f"\nFetching page 1...")
    movies, total_pages = yts.get_movies_page(page=1, minimum_rating=min_rating)
    
    if total_pages == 0:
        print("Error: Could not fetch movies from YTS")
        sys.exit(1)
    
    print(f"Total pages to process: {total_pages:,}")
    
    # Determine actual page range with batch limit
    if max_pages > 0:
        end_page = min(start_page + max_pages - 1, total_pages)
    else:
        # Apply batch size limit to prevent crashes
        end_page = min(start_page + batch_size - 1, total_pages)
    
    print(f"Will process pages {start_page} to {end_page}")
    if end_page < total_pages:
        print(f"NOTE: Processing in batches. After completion, resume from page {end_page + 1}")
    print("="*70)
    
    # Process pages
    for page in range(start_page, end_page + 1):
        try:
            if page > 1:  # Already fetched page 1
                print(f"\n[Page {page}/{end_page}] Fetching movies...")
                movies, _ = yts.get_movies_page(page=page, minimum_rating=min_rating)
                time.sleep(2)  # Rate limiting between pages
            
            if not movies:
                print(f"[Page {page}/{end_page}] No movies found, skipping")
                continue
            
            print(f"[Page {page}/{end_page}] Processing {len(movies)} movies...")
        except Exception as e:
            print(f"\n[Page {page}/{end_page}] ERROR: Failed to fetch page: {e}")
            print("Saving progress and continuing...")
            with open("bulk_fetch_progress.txt", "w") as f:
                f.write(f"Last completed page: {page - 1}\n")
                f.write(f"Last attempted page: {page}\n")
                f.write(f"Total added: {total_added}\n")
                f.write(f"Total skipped: {total_skipped}\n")
                f.write(f"Total failed: {total_failed}\n")
                f.write(f"Error: {str(e)}\n")
            continue
        
        for movie in movies:
            title = movie.get("title", "Unknown")
            year = movie.get("year", "")
            rating = movie.get("rating", 0)
            torrents = movie.get("torrents", [])
            movies_processed += 1
            
            if not torrents:
                total_skipped += 1
                continue
            
            # Show available qualities
            available_qualities = [t.get("quality") for t in torrents]
            
            # Get torrents for all preferred qualities
            torrents_to_add = []
            for quality in preferred_qualities:
                for torrent in torrents:
                    if torrent.get("quality") == quality:
                        torrents_to_add.append(torrent)
                        break
            
            if not torrents_to_add:
                # Log if movie has no matching qualities
                if movies_processed % 10 == 0:  # Every 10th movie to avoid spam
                    print(f"  {title} ({year}): Available [{', '.join(available_qualities)}] - None match")
                total_skipped += 1
                continue
            
            # Add each quality version
            movie_added = False
            qualities_added = []
            for torrent in torrents_to_add:
                torrent_hash = torrent.get("hash", "").lower()
                
                if not torrent_hash or torrent_hash in existing_hashes:
                    continue
                
                # Create magnet link and add to Real-Debrid
                magnet = create_magnet_link(torrent_hash, f"{title} {year} {torrent.get('quality')}")
                
                torrent_id = rd.add_magnet(magnet)
                
                if torrent_id:
                    time.sleep(1)
                    if rd.select_files(torrent_id):
                        total_added += 1
                        movie_added = True
                        qualities_added.append(torrent.get('quality'))
                        existing_hashes.add(torrent_hash)
                    else:
                        total_failed += 1
                else:
                    total_failed += 1
                
                time.sleep(2)  # Rate limiting between requests
            
            # Log what was added
            if movie_added and qualities_added:
                print(f"  ✓ {title} ({year}): Added [{', '.join(qualities_added)}]")
            
            if not movie_added:
                total_skipped += 1
        
        # Progress update
        print(f"[Page {page}/{end_page}] Progress: Added={total_added}, Skipped={total_skipped}, Failed={total_failed}")
        
        # Save progress every 10 pages
        if page % 10 == 0:
            try:
                with open("bulk_fetch_progress.txt", "w") as f:
                    f.write(f"Last completed page: {page}\n")
                    f.write(f"Total added: {total_added}\n")
                    f.write(f"Total skipped: {total_skipped}\n")
                    f.write(f"Total failed: {total_failed}\n")
                    f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            except Exception as e:
                print(f"Warning: Failed to save progress: {e}")
    
    # Final summary
    print("\n" + "="*70)
    batch_complete = end_page >= total_pages
    if batch_complete:
        print("BULK FETCH COMPLETE - ALL PAGES PROCESSED")
    else:
        print(f"BATCH COMPLETE - PAGES {start_page} to {end_page}")
    print("="*70)
    print(f"Finished at: {datetime.now().isoformat()}")
    print(f"Pages processed: {start_page} to {end_page}")
    print(f"Movies processed: {movies_processed:,}")
    print(f"Torrents added to Real-Debrid: {total_added:,}")
    print(f"Torrents skipped (duplicates/no torrents): {total_skipped:,}")
    print(f"Torrents failed: {total_failed:,}")
    
    if not batch_complete:
        print(f"\nTO CONTINUE: Set START_PAGE={end_page + 1} and run again")
        print(f"Remaining pages: {total_pages - end_page}")
    
    print("="*70)
    
    # Mark bulk fetch as complete only if all pages processed
    if batch_complete:
        with open("bulk_fetch_complete.flag", "w") as f:
            f.write(datetime.now().isoformat())
        print("\n✓ Bulk fetch complete flag created - incremental mode will activate")
    
    # Always save final progress
    with open("bulk_fetch_progress.txt", "w") as f:
        f.write(f"Last completed page: {end_page}\n")
        f.write(f"Total pages: {total_pages}\n")
        f.write(f"Batch complete: {batch_complete}\n")
        f.write(f"Total added: {total_added}\n")
        f.write(f"Total skipped: {total_skipped}\n")
        f.write(f"Total failed: {total_failed}\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")


if __name__ == "__main__":
    main()
