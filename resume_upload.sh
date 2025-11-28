#!/bin/bash
# YTS to Real-Debrid - Resume Only (Upload Phase)
# This script assumes YTS and RD hashes are already cached
# Use this to resume interrupted uploads without re-fetching

set -euo pipefail

# --- CONFIGURATION ---
apikey="${REAL_DEBRID_API_TOKEN}"
readonly RD_HEADERS="Authorization: Bearer ${apikey}"
readonly RD_API_URL="https://api.real-debrid.com/rest/1.0/torrents"
readonly PROGRESS_BAR_SIZE=40
readonly PROGRESS_CHAR_DONE="#"
readonly PROGRESS_CHAR_TODO="-"
readonly PROGRESS_BAR_PERCENTAGE_SCALE=2
readonly BATCH_SIZE="${BATCH_SIZE:-10000}" # Process in batches

# --- PROGRESS BAR ---
function show_progress {
    local current="$1"
    local total="$2"

    if ! command -v bc &> /dev/null; then
        return 0
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

# --- CLEAR ACTIVE TORRENTS ---
function clearRDActive {
    echo "Clearing active torrents..."
    mapfile -t active < <(curl -s -X GET -H "$RD_HEADERS" "${RD_API_URL}?limit=500&filter=active" | jq -r '.[].id')
    for id in "${active[@]}"; do
        curl -s -X DELETE -H "$RD_HEADERS" "${RD_API_URL}/delete/$id"
    done
}

# --- MAIN ---
echo "=================================="
echo "YTS Resume Upload Only"
echo "=================================="

# Check for required cache files
if [ ! -f "unique_hashes.txt" ]; then
    echo "ERROR: unique_hashes.txt not found. Run full fetch first."
    exit 1
fi

echo "Loading unique hashes to upload..."
mapfile -t uniqueHashes < unique_hashes.txt
totalcount=${#uniqueHashes[@]}

echo "Total hashes to process: $totalcount"

# Load progress
if [ -f "upload_progress.txt" ]; then
    start_index=$(cat upload_progress.txt)
    echo "Resuming from index: $start_index"
else
    start_index=0
    echo "Starting fresh upload"
fi

# Calculate end index for this batch
end_index=$((start_index + BATCH_SIZE))
if [ $end_index -gt $totalcount ]; then
    end_index=$totalcount
fi

echo "Processing batch: $start_index to $end_index"
echo "=================================="

count=$start_index

for (( i=start_index; i<end_index; i++ )); do
    hash="${uniqueHashes[$i]}"
    
    response=$(curl -s -X POST -H "$RD_HEADERS" -H "application/x-www-form-urlencoded" \
        --data-raw "magnet=magnet:?xt=urn:btih:${hash}" "${RD_API_URL}/addMagnet")

    # Handle errors
    error_code=$(jq -r '.error_code // "none"' <<< "$response")
    
    if [[ "$error_code" == "21" ]]; then 
        clearRDActive
        response=$(curl -s -X POST -H "$RD_HEADERS" -H "application/x-www-form-urlencoded" \
            --data-raw "magnet=magnet:?xt=urn:btih:${hash}" "${RD_API_URL}/addMagnet")
    fi

    while [[ "$error_code" == "34" ]]; do
        echo "Rate limited at $count/$totalcount, waiting 60s..." >&2
        sleep 60
        response=$(curl -s -X POST -H "$RD_HEADERS" -H "application/x-www-form-urlencoded" \
            --data-raw "magnet=magnet:?xt=urn:btih:${hash}" "${RD_API_URL}/addMagnet")
        error_code=$(jq -r '.error_code // "none"' <<< "$response")
    done

    torrentId=$(jq -r '.id' <<< "$response")

    if [[ "$torrentId" == "null" || -z "$torrentId" ]]; then
        echo "$hash" >> failed_hashes.txt
    else
        curl -s -X POST -H "$RD_HEADERS" -H "application/x-www-form-urlencoded" \
            --data-raw "files=all" "${RD_API_URL}/selectFiles/${torrentId}" &>/dev/null || true
    fi
    
    ((count++))
    show_progress "$count" "$totalcount"
    
    # Save progress frequently
    if (( count % 50 == 0 )); then
        echo "$count" > upload_progress.txt
    fi
    
    sleep 1
done

echo "$count" > upload_progress.txt

echo ""
echo "=================================="
if [ "$count" -ge "$totalcount" ]; then
    echo "ALL DONE! Uploaded $count torrents"
    rm -f upload_progress.txt unique_hashes.txt
else
    echo "Batch complete: $count / $totalcount"
    echo "Run again to continue (remaining: $((totalcount - count)))"
fi
echo "=================================="
