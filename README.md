# YTS to Real-Debrid Auto-Fetcher

Automatically fetch the latest movies from YTS and add them to your Real-Debrid account every hour using GitHub Actions.

## Features

- 🎬 Fetches latest movies from YTS API hourly
- 🚀 Automatically adds torrents to Real-Debrid
- ⚙️ Configurable quality, rating, and movie count
- 🔄 Avoids duplicates by checking existing torrents
- 📊 Detailed logging and summaries
- 🎯 Manual trigger support with custom parameters

## Setup Instructions

### 1. Get Your Real-Debrid API Token

1. Go to [Real-Debrid API settings](https://real-debrid.com/apitoken)
2. Log in to your account
3. Copy your API token

### 2. Configure GitHub Repository

1. Fork or create this repository
2. Go to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the following secret:
   - **Name:** `REAL_DEBRID_API_TOKEN`
   - **Value:** Your Real-Debrid API token

### 3. Enable GitHub Actions

1. Go to the **Actions** tab in your repository
2. Click **"I understand my workflows, go ahead and enable them"** if prompted
3. The workflow will now run automatically every hour

## Configuration

You can customize the behavior by modifying the workflow or using manual triggers.

### Default Settings

- **Max Movies:** 10 movies per run
- **Quality:** 1080p
- **Minimum Rating:** 6.5 (IMDB)
- **Schedule:** Every hour (at minute 0)

### Manual Trigger

You can manually trigger the workflow with custom parameters:

1. Go to **Actions** → **Fetch YTS Movies to Real-Debrid**
2. Click **Run workflow**
3. Adjust parameters:
   - Maximum number of movies (default: 10)
   - Quality: 720p, 1080p, or 2160p (default: 1080p)
   - Minimum IMDB rating (default: 6.5)
4. Click **Run workflow**

### Modify Default Settings

Edit `.github/workflows/fetch-movies.yml` and change the environment variables:

```yaml
env:
  MAX_MOVIES: '20'        # Increase to fetch more movies
  QUALITY: '2160p'        # Change to 4K
  MIN_RATING: '7.0'       # Only fetch highly-rated movies
```

### Change Schedule

To run more or less frequently, modify the cron schedule in `.github/workflows/fetch-movies.yml`:

```yaml
schedule:
  - cron: '0 */6 * * *'  # Every 6 hours
  - cron: '0 0 * * *'    # Once daily at midnight
  - cron: '*/30 * * * *' # Every 30 minutes
```

## How It Works

1. **Fetch:** The script queries the YTS API for the latest movies based on your criteria
2. **Filter:** Movies are filtered by quality, rating, and release date
3. **Check:** Existing Real-Debrid torrents are checked to avoid duplicates
4. **Add:** New movie torrents are added to Real-Debrid as magnet links
5. **Select:** All files in the torrent are automatically selected for download
6. **Report:** A summary is logged showing what was added

## Local Testing

You can test the script locally before deploying:

```bash
# Install dependencies
pip install -r requirements.txt

# Set your API token
export REAL_DEBRID_API_TOKEN="your_token_here"

# Optional: Configure settings
export MAX_MOVIES=5
export QUALITY=1080p
export MIN_RATING=7.0

# Run the script
python fetch_movies.py
```

## Monitoring

- View workflow runs in the **Actions** tab
- Check logs for each run to see what movies were added
- Logs are automatically uploaded as artifacts and retained for 7 days

## Troubleshooting

### No movies being added?

- Check that your Real-Debrid account is active
- Verify your API token is correct
- Lower the `MIN_RATING` to include more movies
- Increase `MAX_MOVIES` to fetch more results

### Workflow not running?

- Ensure GitHub Actions are enabled in your repository
- Check the **Actions** tab for error messages
- Free GitHub accounts have usage limits on Actions

### API rate limits?

- YTS and Real-Debrid have rate limits
- Don't run the workflow too frequently (hourly is reasonable)
- The script includes error handling for API failures

## Privacy & Security

- Your Real-Debrid API token is stored securely as a GitHub secret
- Never commit your API token to the repository
- The workflow only runs in your own repository
- No data is shared with third parties

## License

MIT License - Feel free to modify and use as needed.

## Disclaimer

This tool is for educational purposes. Ensure you comply with your local laws regarding torrenting and copyright. The authors are not responsible for misuse of this software.
