#!/usr/bin/env bash

JSON_FILE="playerProfile.json"
OUTPUT_DIR="downloaded_images"
mkdir -p "$OUTPUT_DIR"

# Target the nested .data array
jq -c '.data[]' "$JSON_FILE" | while read -r item; do
  name=$(echo "$item" | jq -r '.name')
  thumbUrl=$(echo "$item" | jq -r '.thumbUrl')
  
  x=$(echo "$item" | jq -r '.thumbReframe.x // empty')
  y=$(echo "$item" | jq -r '.thumbReframe.y // empty')
  w=$(echo "$item" | jq -r '.thumbReframe.width // empty')
  h=$(echo "$item" | jq -r '.thumbReframe.height // empty')
  origW=$(echo "$item" | jq -r '.thumbReframe.originalWidth // empty')
  origH=$(echo "$item" | jq -r '.thumbReframe.originalHeight // empty')

  # Skip entries with missing images or reframe dimensions
  if [ -z "$thumbUrl" ] || [ "$thumbUrl" == "null" ] || [ -z "$x" ]; then
    continue
  fi

  # Calculate crop parameters
  cropW=$(echo "scale=0; ($w * $origW) / 1" | bc)
  cropH=$(echo "scale=0; ($h * $origH) / 1" | bc)
  cropX=$(echo "scale=0; ($x * $origW) / 1" | bc)
  cropY=$(echo "scale=0; ($y * $origH) / 1" | bc)

  # Extract original file extension (.jpeg, .png, etc.)
  ext="${thumbUrl##*.}"
  # Clean up name: "Carlsen, Magnus" -> "Carlsen_Magnus"
  sanitized_name=$(echo "$name" | sed \
    -e 's/^[[:space:]]*//' \
    -e 's/[[:space:]]*$//' \
    -e 's/,/_/g' \
    -e 's/[[:space:]]\+/_/g' \
    -e 's/[^a-zA-Z0-9_-]/_/g' \
    | tr '[:upper:]' '[:lower:]')
  filename="${OUTPUT_DIR}/${sanitized_name}.${ext}"

  cropped_url="${thumbUrl}?crop=${cropW},${cropH},${cropX},${cropY}"

  echo "Downloading ${sanitized_name}.${ext}..."
  curl -s -o "$filename" "$cropped_url"
done

echo "Done! All images saved in ./${OUTPUT_DIR}"
