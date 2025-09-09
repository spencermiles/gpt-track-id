# AI Music Tagger

AI-powered music metadata tagging tool that uses ChatGPT to automatically tag your music files with genres, regions, and eras.

## Setup

### Step 1: Install uv (Python package manager)

Open Terminal and run:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation, restart your terminal or run:
```bash
source ~/.zshrc
```

### Step 2: Get an OpenAI API Key

1. Go to [OpenAI's website](https://platform.openai.com/)
2. Sign up or log in to your account
3. Click on your profile in the top right corner
4. Select "View API Keys" or go to [API Keys page](https://platform.openai.com/account/api-keys)
5. Click "Create new secret key"
6. Give it a name like "Music Tagger"
7. Copy the key (it starts with `sk-proj-...`)

### Step 3: Create a .env file

In the same folder as the `music_tagger.py` file, create a file named `.env` with your API key:
```
OPENAI_API_KEY=sk-proj-your_actual_key_here
```

### Step 4: Run the script

The script will automatically install any needed dependencies:
```bash
uv run music_tagger.py *.mp3
```

## Usage

```bash
# Tag all MP3 files in current directory
uv run music_tagger.py *.mp3

# Tag all audio files in a directory
uv run music_tagger.py /path/to/music

# Tag only files created in the last 7 days
uv run music_tagger.py --since 7d /path/to/music

# Tag only files created in the last 24 hours
uv run music_tagger.py --since 24h /path/to/music

# Tag only files created since a specific date
uv run music_tagger.py --since 2024-01-01 /path/to/music

# Tag specific files
uv run music_tagger.py song1.mp3 song2.m4a

# Dry run to see what would be tagged
uv run music_tagger.py --dry-run *.mp3

# Use API key from command line instead of .env
uv run music_tagger.py --api-key sk-... *.mp3
```

## Output

The tool adds genre tags in the format: `Genre1 - Genre2 - Region - Era`

Example: `House - Deep House - Detroit - 2000s`