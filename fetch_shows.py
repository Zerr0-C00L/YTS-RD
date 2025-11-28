#!/usr/bin/env python3
"""
ShowRSS to Real-Debrid Fetcher
Fetches TV shows from ShowRSS RSS feed and adds them to Real-Debrid
Note: RSS feeds only contain the latest ~100 episodes, not complete series
"""

import os
import sys
import requests
import xml.etree.ElementTree as ET
import re
import time
from datetime import datetime
from typing import List, Dict, Optional


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
                        wait_time = (attempt + 1) * 5
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


def extract_magnet_hash(magnet_link: str) -> Optional[str]:
    """Extract the info hash from a magnet link"""
    match = re.search(r'urn:btih:([a-fA-F0-9]+)', magnet_link)
    if match:
        return match.group(1).lower()
    return None


def parse_rss_feed(rss_url: str) -> List[Dict]:
    """
    Parse ShowRSS feed and extract episode information
    
    Returns:
        List of dictionaries with episode info and magnet links
    """
    try:
        response = requests.get(rss_url, timeout=30)
        response.raise_for_status()
        
        # Parse XML
        root = ET.fromstring(response.content)
        
        episodes = []
        
        # Find all items in the feed
        for item in root.findall('.//item'):
            title_elem = item.find('title')
            link_elem = item.find('link')
            pubdate_elem = item.find('pubDate')
            
            if title_elem is not None and link_elem is not None:
                title = title_elem.text
                magnet_link = link_elem.text
                pub_date = pubdate_elem.text if pubdate_elem is not None else "Unknown"
                
                # Extract hash from magnet link
                torrent_hash = extract_magnet_hash(magnet_link)
                
                if torrent_hash:
                    episodes.append({
                        'title': title,
                        'magnet': magnet_link,
                        'hash': torrent_hash,
                        'pub_date': pub_date
                    })
        
        return episodes
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching RSS feed: {e}")
        return []
    except ET.ParseError as e:
        print(f"Error parsing RSS feed: {e}")
        return []


def main():
    """Main execution function"""
    # Get configuration from environment variables
    rd_api_token = os.getenv("REAL_DEBRID_API_TOKEN")
    rss_url = os.getenv("SHOWRSS_URL", "https://showrss.info/user/76224.rss?magnets=true&namespaces=true&name=clean&quality=fhd&re=yes")
    
    if not rd_api_token:
        print("ERROR: REAL_DEBRID_API_TOKEN environment variable not set")
        sys.exit(1)
    
    print("="*70)
    print("SHOWRSS TO REAL-DEBRID FETCHER")
    print("="*70)
    print(f"Started at: {datetime.now().isoformat()}")
    print(f"Feed: ShowRSS (FHD quality, clean names)")
    print("="*70)
    
    # Initialize Real-Debrid client
    rd = RealDebridClient(rd_api_token)
    
    # Get existing torrents to avoid duplicates
    print("\nFetching existing torrents from Real-Debrid...")
    existing_torrents = rd.get_torrents()
    existing_hashes = {t.get("hash", "").lower() for t in existing_torrents}
    print(f"Found {len(existing_hashes):,} existing torrents in Real-Debrid")
    
    # Fetch and parse RSS feed
    print("\nFetching episodes from ShowRSS feed...")
    episodes = parse_rss_feed(rss_url)
    
    if not episodes:
        print("No episodes found in RSS feed. Exiting.")
        return
    
    print(f"Found {len(episodes)} episodes in feed\n")
    
    # Statistics
    added_count = 0
    skipped_count = 0
    failed_count = 0
    
    # Process each episode
    for episode in episodes:
        title = episode['title']
        magnet = episode['magnet']
        torrent_hash = episode['hash']
        
        print(f"Processing: {title}")
        
        # Check if already added
        if torrent_hash in existing_hashes:
            print(f"  Already in Real-Debrid, skipping")
            skipped_count += 1
            continue
        
        # Add to Real-Debrid
        print(f"  Adding to Real-Debrid...")
        torrent_id = rd.add_magnet(magnet)
        
        if torrent_id:
            time.sleep(1)
            
            # Select all files for download
            if rd.select_files(torrent_id):
                print(f"  ✓ Successfully added (ID: {torrent_id})")
                added_count += 1
                existing_hashes.add(torrent_hash)  # Update local cache
            else:
                print(f"  ✗ Added but failed to select files")
                failed_count += 1
        else:
            print(f"  ✗ Failed to add to Real-Debrid")
            failed_count += 1
        
        # Rate limiting between requests
        time.sleep(2)
    
    # Final summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Episodes processed: {len(episodes)}")
    print(f"Added to Real-Debrid: {added_count}")
    print(f"Skipped (duplicates): {skipped_count}")
    print(f"Failed: {failed_count}")
    print("="*70)


if __name__ == "__main__":
    main()
