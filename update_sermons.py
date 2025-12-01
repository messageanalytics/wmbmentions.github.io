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
        yt = YouTube(url, on_progress_callback=on_progress)
        
        # pytubefix captions are often in XML format, but let's try to get the text
        # We prioritize English ('en') or auto-generated English ('a.en')
        caption = yt.captions.get_by_language_code('en')
        if not caption:
            caption = yt.captions.get_by_language_code('a.en')
            
        if not caption:
            # Fallback: Try to find any english-ish code
            for code in yt.captions:
                if 'en' in code.code:
                    caption = code
                    break
        
        if not caption:
            raise Exception("No English captions found.")

        # Convert to text. generate_srt_captions gives timestamps, we want plain text.
        # We can parse the SRT or XML. Pytubefix often returns XML by default for .xml_captions
        # But .generate_srt_captions() is standard.
        # Let's use a simple regex to strip timestamps from SRT for now.
        srt_text = caption.generate_srt_captions()
        
        # Clean SRT to plain text
        lines = srt_text.splitlines()
        clean_lines = []
        for line in lines:
            # Skip timeline lines (e.g. 00:00:01,000 --> 00:00:04,000)
            if '-->' in line: continue
            # Skip numeric sequence lines
            if line.strip().isdigit(): continue
            # Skip empty lines
            if not line.strip(): continue
            
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
    
    base_channel_url = channel_url.split('/streams')[0].split('/videos')[0].split('/featured')[0]
    
    existing_ids = get_existing_video_ids(filepath)
    print(f"Found {len(existing_ids)} existing videos.")

    all_videos = []
    
    # Scan Streams
    try:
        print("Scanning 'streams'...")
        streams = list(scrapetube.get_channel(channel_url=base_channel_url, content_type='streams', limit=limit))
        print(f"Found {len(streams)} streams.")
        all_videos.extend(streams)
    except: pass

    # Scan Videos
    try:
        print("Scanning 'videos'...")
        uploads = list(scrapetube.get_channel(channel_url=base_channel_url, content_type='videos', limit=limit))
        print(f"Found {len(uploads)} videos.")
        all_videos.extend(uploads)
    except: pass

    unique_videos = {v['videoId']: v for v in all_videos}.values()
    
    if not unique_videos:
        print(f"⚠️ No videos found for {church_name}.")
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