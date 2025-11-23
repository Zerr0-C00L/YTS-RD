# YTS to Real-Debrid Auto-Fetcher

Automatically fetch movies from YTS and add them to your Real-Debrid account using GitHub Actions.

## Features

- 🎬 **Bulk Fetch Mode**: One-time import of all 71,000+ movies from YTS
- ⏰ **Incremental Mode**: Hourly updates to fetch only the latest releases
- 🎯 **All Qualities**: Automatically adds 2160p, 1080p, and 720p versions
- 🔄 **Smart Duplicates**: Checks existing torrents to avoid re-adding
- 📊 **Progress Tracking**: Resume bulk fetch from any page
- 🚀 **Rate Limiting**: Built-in delays to respect API limits

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

## Usage

### Option 1: Bulk Fetch All Movies (Recommended First Step)

To import all ~71,000 movies from YTS:

1. Go to **Actions** → **Bulk Fetch All YTS Movies**
2. Click **Run workflow**
3. Leave defaults (Start Page: 1, Max Pages: 0 for all)
4. Click **Run workflow**

**Important Notes:**
- This will take several hours to complete (~6-10 hours)
- Processes all qualities (2160p, 1080p, 720p) for each movie
- Can be paused and resumed by setting the start page
- Creates a flag file when complete to switch to incremental mode
- Respects rate limits with automatic delays

**To Resume if Interrupted:**
1. Check the artifacts from the last run for `bulk_fetch_progress.txt`
2. Note the last completed page
3. Run workflow again with Start Page = (last page + 1)

### Option 2: Incremental Mode (Automatic After Bulk)

Once bulk fetch is complete, the hourly workflow automatically switches to incremental mode:
- Runs every hour automatically
- Fetches only the latest 20 movies
- Skips movies already in Real-Debrid
- Perfect for keeping your collection up-to-date

You can also run it manually anytime from **Actions** → **Fetch Latest YTS Movies**

## Configuration

You can customize the behavior by modifying the workflow or using manual triggers.

### Default Settings

**Bulk Fetch Mode:**
- Processes all pages (can limit with Max Pages parameter)
- All qualities: 2160p, 1080p, 720p
- No minimum rating (fetches everything)

**Incremental Mode:**
- **Max Movies:** 20 latest movies per run
- **All Qualities:** 2160p, 1080p, 720p
- **Minimum Rating:** 0 (no filter)
- **Schedule:** Every hour (at minute 0)

### Manual Triggers

**Bulk Fetch:**
- **Start Page:** Resume from specific page (default: 1)
- **Max Pages:** Limit pages to process, 0 = all (default: 0)
- **Min Rating:** Filter by rating (default: 0 = all movies)

**Incremental Fetch:**
- **Max Movies:** Number of latest movies to fetch (default: 20)

### Change Hourly Schedule

To run more or less frequently, modify the cron schedule in `.github/workflows/fetch-movies.yml`:

```yaml
schedule:
  - cron: '0 */6 * * *'  # Every 6 hours
  - cron: '0 0 * * *'    # Once daily at midnight
  - cron: '0 */2 * * *'  # Every 2 hours
```

## How It Works

### Bulk Fetch Mode
1. **Paginate:** Iterates through all pages of YTS movies (50 per page)
2. **Extract:** For each movie, gets all quality versions (2160p, 1080p, 720p)
3. **Check:** Compares against up to 100,000 existing torrents in Real-Debrid
4. **Add:** Creates magnet links and adds new torrents to Real-Debrid
5. **Track:** Saves progress every 10 pages for resume capability
6. **Complete:** Creates flag file when done to enable incremental mode

### Incremental Mode
1. **Fetch:** Queries YTS API for latest 20 movies sorted by date added
2. **Check:** Existing Real-Debrid torrents are checked to avoid duplicates
3. **Add:** New movie torrents (all qualities) are added as magnet links
4. **Select:** All files in the torrent are automatically selected for download
5. **Report:** Summary logged showing what was added

## Local Testing

### Test Incremental Fetch
```bash
pip install -r requirements.txt
export REAL_DEBRID_API_TOKEN="your_token_here"
export MAX_MOVIES=5
python fetch_movies.py
```

### Test Bulk Fetch (Limited Pages)
```bash
export REAL_DEBRID_API_TOKEN="your_token_here"
export START_PAGE=1
export MAX_PAGES=2  # Only process 2 pages for testing
python bulk_fetch.py
```

## Monitoring

- View workflow runs in the **Actions** tab
- Check logs for each run to see what movies were added
- Logs are automatically uploaded as artifacts and retained for 7 days

## Troubleshooting

### Bulk fetch is slow or timing out?

- GitHub Actions has a 6-hour timeout for workflows
- Process in batches using MAX_PAGES (e.g., 100 pages at a time)
- Resume from last completed page using START_PAGE parameter
- Rate limiting adds ~2-3 seconds per torrent to respect API limits

### No movies being added?

- Check that your Real-Debrid account is active and has space
- Verify your API token is correct in GitHub Secrets
- Movies may already exist in your Real-Debrid account
- Check the workflow logs for specific error messages

### Getting rate limited (429 errors)?

- The script has built-in retry logic with progressive backoff
- Reduce MAX_MOVIES to process fewer movies per run
- Wait a few minutes and try again
- Consider processing bulk fetch in smaller batches

### Workflow not running?

- Ensure GitHub Actions are enabled in your repository
- Check the **Actions** tab for error messages
- Free GitHub accounts have usage limits on Actions
- Incremental mode only runs after bulk fetch is complete

## Privacy & Security

- Your Real-Debrid API token is stored securely as a GitHub secret
- Never commit your API token to the repository
- The workflow only runs in your own repository
- No data is shared with third parties

## License

MIT License - Feel free to modify and use as needed.

## Performance Notes

- **Bulk Fetch:** Processing all ~71,000 movies takes 6-10 hours
- **Each Movie:** ~6-8 seconds to process (3 qualities × 2 seconds delay)
- **Hourly Incremental:** Completes in 2-5 minutes for 20 movies
- **Duplicates:** Checking 100,000 existing torrents is instant (hash lookup)

## Disclaimer

This tool is for educational purposes. Ensure you comply with your local laws regarding torrenting and copyright. The authors are not responsible for misuse of this software.
