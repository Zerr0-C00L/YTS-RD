#!/bin/bash
# YTS to Real-Debrid Bulk Import Script
# Optimized for GitHub Actions with parallel processing

set -euo pipefail

# --- CONFIGURATION ---
apikey="${REAL_DEBRID_API_TOKEN}"
language="${LANGUAGE:-en}"
rdfile="${RD_CACHE_FILE:-}"

readonly RD_HEADERS="Authorization: Bearer ${apikey}"
readonly RD_API_URL="https://api.real-debrid.com/rest/1.0/torrents"
readonly YTS_URL="https://yts.lt/api/v2/list_movies.json"
readonly YTS_RETRY_LIMIT=5
readonly PROGRESS_BAR_SIZE=40
readonly PROGRESS_CHAR_DONE="#"
readonly PROGRESS_CHAR_TODO="-"
readonly PROGRESS_BAR_PERCENTAGE_SCALE=2

# --- PROGRESS BAR FUNCTION ---
function show_progress {
    local current="$1"
    local total="$2"

    if ! command -v bc &> /dev/null; then
        echo "Error: 'bc' command is not installed." >&2
        return 1
    fi

    local percent
    percent=$(bc <<< "scale=$PROGRESS_BAR_PERCENTAGE_SCALE; 100 * $current / $total")

    local done todo
    done=$(bc <<< "scale=0; $PROGRESS_BAR_SIZE * $percent / 100")
    todo=$(bc <<< "scale=0; $PROGRESS_BAR_SIZE - $done")

    local done_sub_bar todo_sub_bar
    done_sub_bar=$(printf "%${done}s" | tr " " "${PROGRESS_CHAR_DONE}")
    todo_sub_bar=$(printf "%${todo}s" | tr " " "${PROGRESS_CHAR_TODO}")

    echo -ne "\rProgress: [${done_sub_bar}${todo_sub_bar}] ${percent}%"

    if [ "$total" -eq "$current" ]; then
        echo -e "\n"
    fi
}

# --- FETCH YTS PAGE HASHES ---
function yts_get_page_hashes {
    local page="$1"
    local totalPages="$2"
    local retryCount=${3:-0}

    local response
    # Filter for 2160p and 1080p only, prefer 2160p if available
    response=$(curl -s -X GET "${YTS_URL}?page=${page}&limit=50" | \
        jq -r --arg lang "$language" '
        .data.movies[]? | 
        select(.language==$lang and any(.torrents[]; .quality=="1080p" or .quality=="2160p")) | 
        { 
            "torrents": (
                if any(.torrents[]; .quality=="2160p") 
                then [ 
                    (first(.torrents[] | select(.quality=="2160p"))), 
                    (first(.torrents[] | select(.quality=="1080p"))) 
                ] | map(select(. != null)) 
                else [ 
                    (first(.torrents[] | select(.quality=="1080p"))) 
                ] 
                end
            ) 
        } | .torrents[].hash')

    if [ -n "$response" ]; then
        echo "$response"
        show_progress $page $totalPages >&2
    else
        if [ "$retryCount" -lt "$YTS_RETRY_LIMIT" ]; then
            local nextRetry=$((retryCount + 1))
            echo "Retrying page ${page}/${totalPages} (attempt ${nextRetry})..." >&2
            sleep 1
            yts_get_page_hashes "$page" "$totalPages" "$nextRetry"
        else
            echo "Page ${page}/${totalPages} failed after $retryCount attempts." >&2
        fi
    fi
}

# --- CLEAR ACTIVE TORRENTS ---
function clearRDActive {
    echo "Clearing active torrents, active limit reached."
    mapfile -t active < <(curl -s -X GET -H "$RD_HEADERS" "${RD_API_URL}?limit=500&filter=active" | jq -r '.[].id')
    for id in "${active[@]}"; do
        curl -s -X DELETE -H "$RD_HEADERS" "${RD_API_URL}/delete/$id"
    done
}

# --- MAIN EXECUTION ---
echo "=================================="
echo "YTS to Real-Debrid Bulk Import"
echo "=================================="
echo "Language: $language"
echo "Started: $(date)"
echo "=================================="

# --- 1. FETCH EXISTING RD HASHES ---
declare -a rdhashes=()

if [ -f "$rdfile" ]; then
    echo "Using cached Real-Debrid hash file: $rdfile"
    mapfile -t rdhashes < "$rdfile"
else
    echo "Fetching existing torrent hashes from Real-Debrid API..."
    page=1
    while true; do
        echo "Fetching RD Page: $page"
        mapfile -t response_hashes < <(curl -s -X GET -H "$RD_HEADERS" "${RD_API_URL}?limit=5000&page=${page}" | jq -r '.[].hash')

        if [ "${#response_hashes[@]}" -eq 0 ]; then
            break
        fi

        rdhashes+=("${response_hashes[@]}")
        ((page++))
        sleep 0.5
    done
    
    # Cache the hashes for future runs
    printf '%s\n' "${rdhashes[@]}" > rd_hashes_cache.txt
fi

echo "Found ${#rdhashes[@]} existing hashes on Real-Debrid."

# --- 2. FETCH YTS HASHES ---
moviescount=$(curl -s -X GET "$YTS_URL" | jq '.data.movie_count')
pages=$(( (moviescount + 49) / 50 ))
echo "Found $moviescount movies across $pages pages. Starting scrape..."

YTS_RESULTS_FILE=$(mktemp)

for (( page=1; page<=pages; page++ )); do
    yts_get_page_hashes "$page" "$pages" &
done > "$YTS_RESULTS_FILE"
wait

echo "All YTS fetch jobs completed. Processing results..."
mapfile -t ytsHashes < "$YTS_RESULTS_FILE"
rm "$YTS_RESULTS_FILE"
mapfile -t ytsHashes < <(printf '%s\n' "${ytsHashes[@]}" | sort -u)
echo "Found ${#ytsHashes[@]} unique YTS hashes for language '$language'."

# --- 3. FIND AND ADD MISSING HASHES ---
echo "Comparing lists to find unadded torrents..."
mapfile -t uniqueHashes < <(grep -i -v -F -x -f <(printf "%s\n" "${rdhashes[@]}") <(printf "%s\n" "${ytsHashes[@]}"))

totalcount=${#uniqueHashes[@]}
if [ "$totalcount" -eq 0 ]; then
    echo "All torrents are already on Real-Debrid. Nothing to do."
    exit 0
fi

echo "Found $totalcount unadded torrents. Starting upload to Real-Debrid..."
count=0

for hash in "${uniqueHashes[@]}"; do
    response=$(curl -s -X POST -H "$RD_HEADERS" -H "application/x-www-form-urlencoded" \
        --data-raw "magnet=magnet:?xt=urn:btih:${hash}" "${RD_API_URL}/addMagnet")

    # Handle download limit
    if [[ $(jq -r '.error_code' <<< "$response") == "21" ]]; then 
        clearRDActive
        response=$(curl -s -X POST -H "$RD_HEADERS" -H "application/x-www-form-urlencoded" \
            --data-raw "magnet=magnet:?xt=urn:btih:${hash}" "${RD_API_URL}/addMagnet")
    fi

    # Handle rate limiting
    while [[ $(jq -r '.error_code' <<< "$response") == "34" ]]; do
        echo "API rate limited, sleeping for 60s..." >&2
        sleep 60
        response=$(curl -s -X POST -H "$RD_HEADERS" -H "application/x-www-form-urlencoded" \
            --data-raw "magnet=magnet:?xt=urn:btih:${hash}" "${RD_API_URL}/addMagnet")
    done

    torrentId=$(jq -r '.id' <<< "$response")

    if [[ "$torrentId" == "null" || -z "$torrentId" ]]; then
        echo "Torrent ${hash} failed to add. Response: ${response}" >&2
        echo "$hash" >> failed_hashes.txt
    else
        response=$(curl -s -X POST -H "$RD_HEADERS" -H "application/x-www-form-urlencoded" \
            --data-raw "files=all" "${RD_API_URL}/selectFiles/${torrentId}")

        if [[ $(jq -r '.error_code' <<< "$response") == "21" ]]; then 
            clearRDActive
            curl -s -X POST -H "$RD_HEADERS" -H "application/x-www-form-urlencoded" \
                --data-raw "files=all" "${RD_API_URL}/selectFiles/${torrentId}"
        fi
        
        ((count++))
        show_progress "$count" "$totalcount"
    fi
    sleep 1
done

echo ""
echo "=================================="
echo "Script finished!"
echo "Successfully added: $count / $totalcount torrents"
echo "Completed: $(date)"
echo "=================================="
