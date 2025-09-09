#!/usr/bin/env python3
# /// script
# dependencies = [
#     "mutagen>=1.47.0",
#     "openai>=1.0.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
AI-powered music metadata tagging tool
Usage: uv run music_tagger.py [OPTIONS] FILES...
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import random

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3, TCON
    from openai import OpenAI
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Error: Missing required package: {e.name}")
    print("Install with: uv add mutagen openai python-dotenv")
    sys.exit(1)


def extract_metadata(file_path: str) -> Optional[Dict[str, str]]:
    """Extract artist, album, and track title from music file."""
    try:
        audio_file = MutagenFile(file_path)
        if audio_file is None:
            return None
        
        # Try different tag formats
        metadata = {}
        
        # Get artist
        artist = (audio_file.get('TPE1') or audio_file.get('\xa9ART') or 
                 audio_file.get('ARTIST') or audio_file.get('artist'))
        if artist:
            metadata['artist'] = str(artist[0]) if isinstance(artist, list) else str(artist)
        
        # Get album
        album = (audio_file.get('TALB') or audio_file.get('\xa9alb') or 
                audio_file.get('ALBUM') or audio_file.get('album'))
        if album:
            metadata['album'] = str(album[0]) if isinstance(album, list) else str(album)
        
        # Get title
        title = (audio_file.get('TIT2') or audio_file.get('\xa9nam') or 
                audio_file.get('TITLE') or audio_file.get('title'))
        if title:
            metadata['title'] = str(title[0]) if isinstance(title, list) else str(title)
        
        return metadata
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None


def process_batch(batch: List[Dict], api_key: str, batch_num: int, total_batches: int) -> Dict:
    """Process a single batch of tracks and return metadata."""
    print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} tracks)...")
    return get_chatgpt_metadata(batch, api_key)


def get_chatgpt_metadata(tracks: List[Dict], api_key: str) -> Dict:
    """Get metadata from ChatGPT for the given tracks."""
    client = OpenAI(api_key=api_key)
    
    # Format tracks for the prompt
    track_list = []
    for track in tracks:
        artist = track['metadata'].get('artist', 'Unknown')
        album = track['metadata'].get('album', 'Unknown')
        title = track['metadata'].get('title', 'Unknown')
        track_list.append(f"Artist: {artist} | Track: {title} | Album: {album}")
    
    tracks_text = '\n'.join(track_list)
    
    prompt = f"""
<TASK>
You're a DJ, categorizing your digital collection into various tags for efficient recall during sets. For the following tracks, please return the following fields:
- genres (>=1, House, Lo-fi House, Leftfield House, Deep House, Tech House, Minimal, Techno, Dub Techno, Acid House, Acid Techno, Dub, Hip Hop, Rap, R&B, Dubstep, UK Bass, Bass, UK Garage, Disco, Ambient, Experimental, Hypnotic, Electro, Trance, Italo, Edits, Drum & Bass, Jungle, Breaks, Happy Hardcore, IDM, Footwork, Reggae, Pop)
- region (>=1, Detroit, Chicago, NYC, US, UK, Europe, Berlin, Japan, Italy, Canada, Australia, Latin America, Africa)
- era (60s, 70s, 80s, 90s, 2000s, 2010s, 2020s)
</TASK>

<CONSTRAINTS>
- Only include the results when you have high certainty.
- If unsure, omit the field.
- Region can have multiple values. If a city is present, it should also also the parent region, i.e. ["Chicago", "US"]
</CONSTRAINTS>

<OUTPUT_FORMAT>
Return the results as JSON in this format:
{{
  "Artist - Track": {{
    "genres": ["genre1", "genre2"],
    "region": ["region1", "region2"],
    "era": "era"
  }}
}}
</OUTPUT_FORMAT>

<tracks>
{tracks_text}
</tracks>"""

    max_retries = 5
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[{"role": "user", "content": prompt}],
                reasoning_effort="minimal"
            )
                    
            # Try to parse JSON response
            response_text = response.choices[0].message.content.strip()
            
            # Extract JSON from response (in case there's extra text)
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_text = response_text[start_idx:end_idx]
                return json.loads(json_text)
            else:
                print("Error: Could not parse JSON from ChatGPT response")
                return {}
                
        except Exception as e:
            error_str = str(e)
            if "rate_limit_exceeded" in error_str or "429" in error_str:
                if attempt < max_retries - 1:
                    # Extract wait time from error message if available
                    wait_time = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    
                    # Try to extract suggested wait time from error message
                    if "Please try again in" in error_str:
                        try:
                            import re
                            match = re.search(r'Please try again in (\d+)ms', error_str)
                            if match:
                                suggested_wait = int(match.group(1)) / 1000.0
                                wait_time = max(wait_time, suggested_wait)
                        except:
                            pass
                    
                    print(f"Rate limit hit, waiting {wait_time:.1f}s before retry {attempt + 1}/{max_retries}")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"Rate limit exceeded after {max_retries} attempts: {e}")
                    return {}
            else:
                print(f"Error calling ChatGPT API: {e}")
                return {}
    
    return {}


def update_genre_tag(file_path: str, tags: List[str]) -> bool:
    """Update the genre tag in the music file, adding to existing genres."""
    try:
        audio_file = MutagenFile(file_path)
        if audio_file is None:
            return False
        
        # Get existing genre tags
        existing_genres = []
        
        # Handle ID3 tags (MP3)
        if hasattr(audio_file, 'add_tags'):
            if audio_file.tags is None:
                audio_file.add_tags()
            if 'TCON' in audio_file.tags:
                existing_text = str(audio_file.tags['TCON'])
                if existing_text:
                    existing_genres = [g.strip() for g in existing_text.split(' - ')]
        # Handle other formats
        elif 'TCON' in audio_file:
            # TCON can be a list, handle properly
            if audio_file['TCON']:
                if isinstance(audio_file['TCON'], list):
                    existing_text = str(audio_file['TCON'][0])
                else:
                    existing_text = str(audio_file['TCON'])
                if existing_text and not existing_text.startswith('['):
                    existing_genres = [g.strip() for g in existing_text.split(' - ')]
        elif '\xa9gen' in audio_file:  # M4A
            existing_text = str(audio_file['\xa9gen'][0]) if audio_file['\xa9gen'] else ''
            if existing_text:
                existing_genres = [g.strip() for g in existing_text.split(' - ')]
        elif 'GENRE' in audio_file:
            existing_text = str(audio_file['GENRE'][0]) if audio_file['GENRE'] else ''
            if existing_text:
                existing_genres = [g.strip() for g in existing_text.split(' - ')]
        
        # Combine existing and new tags, remove duplicates while preserving order
        all_tags = existing_genres + tags
        unique_tags = list(dict.fromkeys(all_tags))
        
        # Create combined genre string
        genre_string = ' - '.join(unique_tags)
        
        # Update the appropriate field based on file type
        file_type = type(audio_file).__name__
        
        if file_type == 'MP4':
            # M4A/ALAC files - write to ©gen field
            audio_file['\xa9gen'] = [genre_string]
        elif file_type in ['MP3', 'AIFF'] or hasattr(audio_file, 'add_tags'):
            # MP3 and AIFF files with ID3 tags
            if audio_file.tags is None:
                audio_file.add_tags()
            audio_file.tags['TCON'] = TCON(encoding=3, text=genre_string)
        elif 'TCON' in audio_file:
            audio_file['TCON'] = [genre_string]
        else:
            # Generic approach for other formats
            audio_file['GENRE'] = [genre_string]
        
        audio_file.save()
        return True
        
    except Exception as e:
        print(f"Error updating {file_path}: {e}")
        return False


def find_audio_files(path: str, since_date: Optional[datetime] = None) -> List[str]:
    """Find audio files in a directory, optionally filtered by creation date."""
    audio_extensions = {'.mp3', '.m4a', '.flac', '.wav', '.aac', '.ogg', '.wma'}
    files = []
    
    path_obj = Path(path)
    if path_obj.is_file():
        return [path]
    
    if not path_obj.is_dir():
        return []
    
    for file_path in path_obj.rglob('*'):
        if file_path.suffix.lower() in audio_extensions:
            if since_date:
                # Get creation time (birth time on macOS, ctime on others)
                try:
                    if hasattr(os.stat_result, 'st_birthtime'):
                        # macOS - use birth time
                        stat = file_path.stat()
                        created = datetime.fromtimestamp(stat.st_birthtime)
                    else:
                        # Linux/Windows - use ctime as best approximation
                        stat = file_path.stat()
                        created = datetime.fromtimestamp(stat.st_ctime)
                    
                    if created >= since_date:
                        files.append(str(file_path))
                except (OSError, AttributeError):
                    # If we can't get creation time, skip the file
                    continue
            else:
                files.append(str(file_path))
    
    return sorted(files)


def parse_since_date(since_str: str) -> datetime:
    """Parse --since argument into datetime."""
    if since_str.endswith('d'):
        # Days ago (e.g., "7d")
        days = int(since_str[:-1])
        return datetime.now() - timedelta(days=days)
    elif since_str.endswith('h'):
        # Hours ago (e.g., "24h")
        hours = int(since_str[:-1])
        return datetime.now() - timedelta(hours=hours)
    else:
        # Try to parse as ISO date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
        try:
            return datetime.fromisoformat(since_str)
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid date format: {since_str}. Use YYYY-MM-DD, Nd (N days ago), or Nh (N hours ago)")


def main():
    # Load environment variables from .env file if present
    load_dotenv()
    
    parser = argparse.ArgumentParser(description='AI-powered music metadata tagging')
    parser.add_argument('files', nargs='+', help='Music files or directories to process')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--api-key', help='OpenAI API key (or set OPENAI_API_KEY env var)')
    parser.add_argument('--since', type=parse_since_date, help='Only process files created since this date/time. Format: YYYY-MM-DD, 7d (7 days ago), or 24h (24 hours ago)')
    parser.add_argument('--workers', type=int, default=5, help='Number of parallel workers for processing batches (default: 5)')
    
    args = parser.parse_args()
    
    # Get API key
    api_key = args.api_key or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: OpenAI API key required. Set OPENAI_API_KEY or use --api-key")
        sys.exit(1)
    
    # Collect all audio files
    all_files = []
    for path in args.files:
        if not Path(path).exists():
            print(f"Warning: Path not found: {path}")
            continue
        
        files = find_audio_files(path, args.since)
        all_files.extend(files)
    
    if args.since and all_files:
        print(f"Found {len(all_files)} audio files created since {args.since.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Process files
    tracks = []
    for file_path in all_files:
        metadata = extract_metadata(file_path)
        if metadata:
            tracks.append({
                'file_path': file_path,
                'metadata': metadata
            })
        else:
            print(f"Warning: Could not read metadata from {file_path}")
    
    if not tracks:
        print("No valid music files found")
        sys.exit(1)
    
    print(f"Processing {len(tracks)} tracks...")
    
    # Process tracks in batches of 10 with parallel workers
    ai_metadata = {}
    batch_size = 10
    total_batches = (len(tracks) + batch_size - 1) // batch_size
    
    # Create batches
    batches = []
    for i in range(0, len(tracks), batch_size):
        batch = tracks[i:i + batch_size]
        batch_num = i // batch_size + 1
        batches.append((batch, batch_num))
    
    # Process batches in parallel
    print(f"Processing {len(tracks)} tracks in {total_batches} batches using {args.workers} workers...")
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all batches
        future_to_batch = {
            executor.submit(process_batch, batch, api_key, batch_num, total_batches): batch_num 
            for batch, batch_num in batches
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_batch):
            batch_num = future_to_batch[future]
            try:
                batch_metadata = future.result()
                ai_metadata.update(batch_metadata)
                print(f"Completed batch {batch_num}/{total_batches}")
            except Exception as e:
                print(f"Error processing batch {batch_num}: {e}")
    
    # Process results
    for track in tracks:
        artist = track['metadata'].get('artist', 'Unknown')
        title = track['metadata'].get('title', 'Unknown')
        track_key = f"{artist} - {title}"
        
        if track_key in ai_metadata:
            tags = []
            metadata = ai_metadata[track_key]
            
            # Add genres
            if 'genres' in metadata:
                tags.extend(metadata['genres'])
            
            # Add region
            if 'region' in metadata:
                if isinstance(metadata['region'], list):
                    tags.extend(metadata['region'])
                else:
                    tags.append(metadata['region'])
            
            # Add era
            if 'era' in metadata:
                tags.append(metadata['era'])
            
            if tags:
                # Remove duplicates while preserving order
                unique_tags = list(dict.fromkeys(tags))
                
                if args.dry_run:
                    print(f"{track['file_path']}: Would add tags: {' - '.join(unique_tags)}")
                else:
                    if update_genre_tag(track['file_path'], unique_tags):
                        print(f"{track['file_path']}: Added tags: {' - '.join(unique_tags)}")
                    else:
                        print(f"{track['file_path']}: Failed to update tags")
            else:
                print(f"{track['file_path']}: No tags found")
        else:
            print(f"{track['file_path']}: No AI metadata found")


if __name__ == '__main__':
    main()