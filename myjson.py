import json
import os
import re

# ============================================================
# CONFIGURATION
# ============================================================

JSON_FILE = "playerProfile.json"
IMAGE_DIR = "playerImages"

# Change this to whatever URL your images will use
IMAGE_BASE_URL = "playerImages/"

OUTPUT_FILE = "playerProfile_updated.json"


# ============================================================
# NAME -> IMAGE NAME
# ============================================================

def name_to_filename(name):
    """
    Carlsen, Magnus -> carlsen__magnus
    Abasov, Nijat   -> abasov__nijat
    Adireddy, Arjun -> adireddy__arjun
    """

    name = name.strip().lower()

    if "," in name:
        last_name, first_name = name.split(",", 1)

        last_name = re.sub(
            r"[^a-z0-9]+",
            "_",
            last_name.strip()
        ).strip("_")

        first_name = re.sub(
            r"[^a-z0-9]+",
            "_",
            first_name.strip()
        ).strip("_")

        return f"{last_name}__{first_name}"

    # Fallback
    name = re.sub(r"[^a-z0-9]+", "_", name)

    return name.strip("_")


# ============================================================
# FIND PLAYER LIST AUTOMATICALLY
# ============================================================

def find_players(data):

    # Case 1:
    # Direct list
    if isinstance(data, list):
        return data

    # Case 2:
    # {"data": [...]}
    if isinstance(data, dict):

        if isinstance(data.get("data"), list):
            return data["data"]

        # Case 3:
        # {"data": {"data": [...]}}
        if isinstance(data.get("data"), dict):

            nested = data["data"]

            if isinstance(nested.get("data"), list):
                return nested["data"]

        # Search recursively
        for value in data.values():

            if isinstance(value, list):

                # Check whether it looks like player data
                if value and isinstance(value[0], dict):

                    if "name" in value[0]:
                        return value

            elif isinstance(value, dict):

                result = find_players(value)

                if result is not None:
                    return result

    return None


# ============================================================
# LOAD JSON
# ============================================================

with open(JSON_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)


players = find_players(data)

if players is None:
    raise ValueError(
        "Could not find player list in JSON file."
    )


print(f"Found {len(players)} players.")


# ============================================================
# BUILD IMAGE LOOKUP
# ============================================================

image_lookup = {}

for filename in os.listdir(IMAGE_DIR):

    full_path = os.path.join(
        IMAGE_DIR,
        filename
    )

    if not os.path.isfile(full_path):
        continue

    name, extension = os.path.splitext(filename)

    extension = extension.lower()

    if extension not in [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp"
    ]:
        continue

    normalized_name = name.lower().strip()

    image_lookup[normalized_name] = filename


print(f"Found {len(image_lookup)} images.")


# ============================================================
# MATCH PLAYERS
# ============================================================

matched = 0
not_found = 0


for player in players:

    player_name = player.get("name", "").strip()

    if not player_name:
        continue

    expected_name = name_to_filename(player_name)

    image_filename = image_lookup.get(
        expected_name
    )

    if image_filename:

        old_url = player.get("thumbUrl")

        new_url = (
            IMAGE_BASE_URL +
            image_filename
        )

        player["thumbUrl"] = new_url

        matched += 1

        print(
            f"[MATCH] {player_name}"
        )

        print(
            f"        {image_filename}"
        )

    else:

        not_found += 1

        print(
            f"[NOT FOUND] {player_name}"
        )

        print(
            f"            Expected: {expected_name}"
        )


# ============================================================
# SAVE
# ============================================================

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        data,
        f,
        indent=2,
        ensure_ascii=False
    )


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 50)
print("DONE")
print("=" * 50)

print(
    f"Total players : {len(players)}"
)

print(
    f"Matched       : {matched}"
)

print(
    f"Not found     : {not_found}"
)

print(
    f"Output        : {OUTPUT_FILE}"
)