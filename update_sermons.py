import os
import re
import json
import datetime
import argparse
import scrapetube
from pytubefix import YouTube
from pytubefix.cli import on_progress

# --- CONFIGURATION ---
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

def get_transcript_text(video_id):
    """
    Fetches transcript using pytubefix.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        # Initialize YouTube object
        # use_oauth=False helps avoid login prompts in headless mode
        yt = YouTube(url, use_oauth=False, allow_oauth_cache=False, on_progress_callback=on_progress)
        
        # 1. Try standard English captions
        caption = None
        try:
            caption = yt.captions['en']
        except:
            pass
            
        # 2. Try auto-generated English ('a.en')
        if not caption:
            try:
                caption = yt.captions['a.en']
            except:
                pass
        
        # 3. Fallback: Search for any code containing 'en'
        if not caption:
            for code in yt.captions:
                if 'en' in code.code:
                    caption = code
                    break
        
        if not caption:
            # List available codes for debugging
            available = [c.code for c in yt.captions]
            raise Exception(f"No English captions found. Available: {available}")

        # Generate SRT (Timed Text)
        srt_text = caption.generate_srt_captions()
        
        # Clean SRT to plain text (remove timestamps and line numbers)
        lines = srt_text.splitlines()
        clean_lines = []
        for line in lines:
            if '-->' in line: continue      # Skip timestamps
            if line.strip().isdigit(): continue # Skip sequence numbers
            if not line.strip(): continue       # Skip empty lines
            clean_lines.append(line.strip())
            
        return " ".join(clean_lines)

    except Exception as e:
        raise e

def process_channel(church_name, config, limit=10):
    channel_url = config['url']
    filename = config['filename']
    filepath = os.path.join(DATA_DIR, filename)
    
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"\n--------------------------------------------------")
    print(f"Processing Channel: {church_name}")
    
    # Remove sub-paths to ensure we scan the root channel
    base_channel_url = channel_url.split('/streams')[0].split('/videos')[0].split('/featured')[0]
    
    existing_ids = get_existing_video_ids(filepath)
    print(f"Found {len(existing_ids)} existing videos in database.")

    all_videos = []
    
    # Scan Streams tab
    try:
        print("Scanning 'streams'...")
        streams = list(scrapetube.get_channel(channel_url=base_channel_url, content_type='streams', limit=limit))
        print(f"Found {len(streams)} streams.")
        all_videos.extend(streams)
    except: pass

    # Scan Videos tab
    try:
        print("Scanning 'videos'...")
        uploads = list(scrapetube.get_channel(channel_url=base_channel_url, content_type='videos', limit=limit))
        print(f"Found {len(uploads)} videos.")
        all_videos.extend(uploads)
    except: pass

    # Deduplicate
    unique_videos = {v['videoId']: v for v in all_videos}.values()
    
    if not unique_videos:
        print(f"⚠️ No videos found for {church_name}. Check URL.")
        return

    print(f"Total unique videos to check: {len(unique_videos)}")
    
    new_entries = []
    fallback_date = datetime.datetime.now().strftime("%Y-%m-%d")

    for video in unique_videos:
        video_id = video['videoId']
        try: title = video['title']['runs'][0]['text']
        except: title = "Unknown Title"
        
        if video_id in existing_ids:
            continue

        print(f"NEW CONTENT FOUND: {title} ({video_id})")

        try:
            text_formatted = get_transcript_text(video_id)
            entry = format_sermon_entry(video_id, title, fallback_date, text_formatted, church_name)
            new_entries.append(entry)
            print(f"✅ Transcript downloaded.")
            
        except Exception as e:
            print(f"❌ Skipping {video_id}: {str(e)}")

    if new_entries:
        print(f"Writing {len(new_entries)} new sermons to {filepath}...")
        with open(filepath, 'a', encoding='utf-8') as f:
            for entry in reversed(new_entries):
                f.write(entry)
        print(f"SUCCESS: {filename} updated.")
    else:
        print(f"No new transcripts for {church_name}.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()

    channels = load_config()
    if not channels: return

    for name, config in channels.items():
        process_channel(name, config, args.limit)

if __name__ == "__main__":
    main()