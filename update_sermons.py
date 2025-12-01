import os
import re
import json
import datetime
import argparse
import scrapetube
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

# --- CONFIGURATION ---
# We prioritize channels.json as the standard name
CONFIG_FILES = ["channels.json", "config.json"]
DATA_DIR = "data"

def load_config():
    for config_file in CONFIG_FILES:
        if os.path.exists(config_file):
            print(f"Loading configuration from: {config_file}")
            with open(config_file, 'r') as f:
                return json.load(f)
    
    print(f"ERROR: No configuration file found. Checked: {CONFIG_FILES}")
    return {}

def get_existing_video_ids(filepath):
    if not os.path.exists(filepath):
        return set()
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    # Matches: youtube.com/watch?v=ID
    ids = set(re.findall(r'youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})', content))
    return ids

def format_sermon_entry(video_id, title, date_str, transcript_text, church_name):
    speaker = "Unknown Speaker"
    if "Evans" in title: speaker = "Brother Daniel Evans"
    elif "Brisson" in title: speaker = "Brother Steeve Brisson"
    elif "Guerra" in title: speaker = "Brother Aaron Guerra"
    elif "Branham" in title: speaker = "Brother William Branham"
    
    header = f"""
################################################################################
START OF FILE: {date_str} - {title} - {speaker} - Clean.txt
################################################################################

SERMON DETAILS
========================================
Date:    {date_str}
Title:   {title}
Speaker: {speaker}
Church:  {church_name}
URL:     https://www.youtube.com/watch?v={video_id}
========================================

"""
    return header + transcript_text + "\n"

def process_channel(church_name, config, limit=10):
    channel_url = config['url']
    filename = config['filename']
    filepath = os.path.join(DATA_DIR, filename)
    
    # Ensure data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"\n--------------------------------------------------")
    print(f"Processing Channel: {church_name}")
    print(f"URL: {channel_url}")
    print(f"Target File: {filepath}")

    existing_ids = get_existing_video_ids(filepath)
    print(f"Found {len(existing_ids)} existing videos in database.")

    # 1. Try fetching based on URL type first
    c_type = 'streams' if '/streams' in channel_url else 'videos'
    print(f"Attempting to scrape '{c_type}'...")
    
    try:
        videos = list(scrapetube.get_channel(channel_url=channel_url, content_type=c_type, limit=limit))
    except Exception as e:
        print(f"Error scraping {c_type}: {e}")
        videos = []

    # 2. Fallback: If 0 videos found, try the OTHER type
    if not videos:
        fallback_type = 'videos' if c_type == 'streams' else 'streams'
        print(f"No videos found in '{c_type}'. Trying '{fallback_type}'...")
        # Remove specific path for fallback check
        base_url = channel_url.replace('/streams', '').replace('/videos', '')
        try:
            videos = list(scrapetube.get_channel(channel_url=base_url, content_type=fallback_type, limit=limit))
        except Exception as e:
            print(f"Error scraping {fallback_type}: {e}")

    if not videos:
        print(f"No videos found for {church_name} (checked both streams and uploads). Check URL.")
        return

    print(f"Scrapetube found {len(videos)} videos. Checking for new content...")
    
    new_entries = []
    fallback_date = datetime.datetime.now().strftime("%Y-%m-%d")

    for video in videos:
        video_id = video['videoId']
        
        # Safely extract title
        try:
            title = video['title']['runs'][0]['text']
        except:
            title = "Unknown Title"
        
        if video_id in existing_ids:
            # print(f"Skipping existing: {title}") # Uncomment for verbose logs
            continue

        print(f"NEW SERMON FOUND: {title} ({video_id})")

        try:
            # Fetch Transcript
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Try manual English, fallback to auto-generated
            try:
                transcript = transcript_list.find_manually_created_transcript(['en'])
            except:
                transcript = transcript_list.find_generated_transcript(['en'])
            
            transcript_data = transcript.fetch()
            formatter = TextFormatter()
            text_formatted = formatter.format_transcript(transcript_data)
            
            entry = format_sermon_entry(video_id, title, fallback_date, text_formatted, church_name)
            new_entries.append(entry)
            print(f"Transcript downloaded successfully.")
            
        except Exception as e:
            print(f" Skipping {video_id} (No transcript/Error): {e}")

    if new_entries:
        print(f"Writing {len(new_entries)} new sermons to {filepath}...")
        # Append to file
        with open(filepath, 'a', encoding='utf-8') as f:
            for entry in reversed(new_entries):
                f.write(entry)
        print(f"SUCCESS: {filename} updated.")
    else:
        print(f"No new transcripts to add for {church_name}.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=10, help='Max videos to check per channel')
    args = parser.parse_args()

    print("Starting Update Script...")
    channels = load_config()
    
    if not channels:
        print("EXITING: No channels found.")
        return

    print(f"Found {len(channels)} channels in config.")

    for name, config in channels.items():
        process_channel(name, config, args.limit)

if __name__ == "__main__":
    main()