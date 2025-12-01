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
    raw_url = config['url']
    filename = config['filename']
    filepath = os.path.join(DATA_DIR, filename)
    
    # Ensure data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"\n--------------------------------------------------")
    print(f"Processing Channel: {church_name}")
    
    # Clean URL to get base channel URL (remove /streams, /videos, /featured)
    base_channel_url = raw_url.split('/streams')[0].split('/videos')[0].split('/featured')[0]
    print(f"Base URL: {base_channel_url}")

    existing_ids = get_existing_video_ids(filepath)
    print(f"Found {len(existing_ids)} existing videos in database.")

    # Collect videos from BOTH 'streams' and 'videos' tabs
    all_videos = []
    
    print(f"Scanning 'streams' tab...")
    try:
        streams = list(scrapetube.get_channel(channel_url=base_channel_url, content_type='streams', limit=limit))
        print(f"Found {len(streams)} streams.")
        all_videos.extend(streams)
    except Exception as e:
        print(f"Error fetching streams: {e}")

    print(f"Scanning 'videos' tab...")
    try:
        uploads = list(scrapetube.get_channel(channel_url=base_channel_url, content_type='videos', limit=limit))
        print(f"Found {len(uploads)} videos.")
        all_videos.extend(uploads)
    except Exception as e:
        print(f"Error fetching videos: {e}")

    # Deduplicate by videoId (just in case)
    unique_videos = {v['videoId']: v for v in all_videos}.values()
    
    if not unique_videos:
        print(f"No videos found for {church_name}. Check URL or channel privacy.")
        return

    print(f"Total unique videos to check: {len(unique_videos)}")
    
    new_entries = []
    fallback_date = datetime.datetime.now().strftime("%Y-%m-%d")

    for video in unique_videos:
        video_id = video['videoId']
        
        # Safely extract title
        try:
            title = video['title']['runs'][0]['text']
        except:
            title = "Unknown Title"
        
        if video_id in existing_ids:
            # print(f"Skipping existing: {title}") # Uncomment for verbose logs
            continue

        print(f"NEW CONTENT FOUND: {title} ({video_id})")

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
            print(f"Skipping {video_id} (No transcript/Error): {e}")

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