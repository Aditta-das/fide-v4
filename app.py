import os
import json
import time
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="FIDE DATA FETCHER")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://gmbangladesh.com",
        "https://www.gmbangladesh.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "playerProfile_updated.json")
IMAGES_DIR = os.path.join(BASE_DIR, "playerImages")
os.makedirs(IMAGES_DIR, exist_ok=True)

app.mount("/playerImages", StaticFiles(directory=IMAGES_DIR), name="playerImages")


@app.get("/")
def home():
    return RedirectResponse(url="/docs")


# ── Local players DB ────────────────────────────────────────────────
def load_players():
    """
    Loads playerProfile_updated.json and returns a flat list of player dicts.
    Handles both:
      - a raw list:            [ {...}, {...} ]
      - a wrapped object:      { "data": [ {...}, {...} ] }
    """
    if not os.path.exists(DB_PATH):
        return []

    with open(DB_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict) and "data" in raw:
        raw = raw["data"]

    if isinstance(raw, dict):
        raw = list(raw.values())

    # keep only actual player dicts, drop any malformed entries
    return [p for p in raw if isinstance(p, dict)]


def save_players(players):
    """Saves back in the same {"data": [...]} shape the file already uses."""
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump({"data": players}, f, indent=2, ensure_ascii=False)


class Player(BaseModel):
    fideId: int
    name: str
    federation: Optional[str] = None
    title: Optional[str] = None
    sex: Optional[str] = None
    birthYear: Optional[int] = None
    thumbUrl: Optional[str] = None
    blitz: Optional[int] = None
    rapid: Optional[int] = None
    std: Optional[int] = None


def name_to_search_form(name: str) -> str:
    """
    Converts a stored "Last, First" name into "First Last" form.
    "Carlsen, Magnus" -> "Magnus Carlsen"
    Names without a comma are returned unchanged.
    """
    name = name.strip()
    if "," in name:
        last, _, first = name.partition(",")
        return f"{first.strip()} {last.strip()}"
    return name


def to_token_set(n: str):
    """Turns any name format into a comparable set of lowercase tokens."""
    n = n.strip().lower()
    if "," in n:
        last, _, first = n.partition(",")
        n = f"{first.strip()} {last.strip()}"
    return set(n.split())


def find_player_by_name(players, name):
    if not name:
        return None

    clean_players = [p for p in players if isinstance(p, dict)]
    name = name.strip()
    name_lower = name.lower()

    # 1. exact match, as stored
    for p in clean_players:
        if p.get("name", "").strip().lower() == name_lower:
            return p

    # 2. token-set match — handles "Magnus Carlsen" == "Carlsen, Magnus"
    target_tokens = to_token_set(name)
    for p in clean_players:
        p_tokens = to_token_set(p.get("name", ""))
        if p_tokens and p_tokens == target_tokens:
            return p

    # 3. loose fallback: smaller token set is a subset of the larger
    for p in clean_players:
        p_tokens = to_token_set(p.get("name", ""))
        if not p_tokens:
            continue
        smaller, larger = (
            (target_tokens, p_tokens) if len(target_tokens) <= len(p_tokens) else (p_tokens, target_tokens)
        )
        if smaller and smaller.issubset(larger):
            return p

    return None


def resolve_player_output(player: dict, request: Request) -> dict:
    """Adds a displayName ('First Last') and makes thumbUrl a full absolute URL."""
    player = dict(player)

    if player.get("name"):
        player["displayName"] = name_to_search_form(player["name"])

    thumb = player.get("thumbUrl")
    if thumb and not thumb.startswith(("http://", "https://")):
        base_url = str(request.base_url)
        player["thumbUrl"] = base_url.rstrip("/") + "/" + thumb.lstrip("/")

    return player


@app.get("/players")
def get_players(request: Request):
    players = load_players()
    players = [resolve_player_output(p, request) for p in players]
    return {"ok": True, "data": players}


@app.get("/players/by-name")
def get_player_by_name(request: Request, name: str = Query(...)):
    players = load_players()
    player = find_player_by_name(players, name)
    if not player:
        return {"ok": False, "data": None}
    player = resolve_player_output(player, request)
    return {"ok": True, "data": player}


@app.post("/players")
def create_player(player: Player):
    players = load_players()
    if any(p.get("fideId") == player.fideId for p in players):
        raise HTTPException(status_code=409, detail="Player already exists")

    new_player = {
        "fideId": player.fideId,
        "name": player.name,
        "federation": player.federation,
        "title": player.title,
        "sex": player.sex,
        "birthYear": player.birthYear,
        "thumbUrl": player.thumbUrl,
        "rating": {
            "blitz": player.blitz,
            "rapid": player.rapid,
            "std": player.std,
        },
    }

    players.append(new_player)
    save_players(players)
    return {"ok": True, "data": new_player}


@app.get("/top_players")
def get_top_players(limit: int = 100, gender: str = "women/open"):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://ratings.fide.com/a_top.php?list={gender}"
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.select_one(".top_recors_table")
        rows = table.find_all("tr")
        rows.pop(0)
        top_players = []
        for i, row in enumerate(rows):
            if i + 1 <= limit:
                raw_row = []
                for column in row.find_all("td"):
                    raw_data = column.get_text().replace("\xa0", "")
                    raw_row.append(raw_data)
                    player_url = column.find("a")
                    if player_url:
                        raw_row.append(player_url["href"].split("/")[-1])
                top_players.append({
                    "rank": raw_row[0], "name": raw_row[1], "fide_id": raw_row[2],
                    "country": raw_row[3].strip(), "rating": raw_row[4],
                })
        return top_players
    except Exception as e:
        return {"error": str(e)}


@app.get("/top_country_players")
def get_top_country_players(limit: int = 100, country: str = "BAN", gender: str = "M"):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://ratings.fide.com/",
        }
        url = (
            "https://ratings.fide.com/a_top_var.php"
            f"?continent=&country={country}&rating=&gender={gender}&age1=&age2=&period=&period2="
        )
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.find_all("tr")
        rows.pop(0)
        top_country_players = []
        for i, row in enumerate(rows):
            if i + 1 <= limit:
                raw_row = []
                for column in row.find_all("td"):
                    raw_data = column.get_text().replace("\xa0", "")
                    raw_row.append(raw_data)
                    player_url = column.find("a")
                    if player_url:
                        raw_row.append(player_url["href"].split("/")[-1])
                top_country_players.append({
                    "rank": raw_row[0], "name": raw_row[1], "fide_id": raw_row[2],
                    "country": raw_row[3].strip(), "rating": raw_row[4],
                })
        return top_country_players
    except Exception as e:
        return {"error": str(e)}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://ratings.fide.com/rated_tournaments.phtml",
}
session = requests.Session()
session.headers.update(HEADERS)


def fetch_fide_json(url: str):
    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()
        text = response.content.decode("utf-8-sig")
        return json.loads(text)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"FIDE request failed: {e}")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON from FIDE: {e}")


@app.get("/tournaments")
def get_tournaments():
    url = f"https://ratings.fide.com/a_tournaments.php?country=all&_={int(time.time() * 1000)}"
    data = fetch_fide_json(url)
    tournaments = []
    today = datetime.now().date()
    for row in data.get("data", []):
        try:
            start_date = datetime.strptime(row[4], "%Y-%m-%d").date()
            end_date = datetime.strptime(row[5], "%Y-%m-%d").date() if row[5] else start_date
            if end_date < today:
                continue
            tournaments.append({
                "id": row[0], "name": row[1], "location": row[2],
                "start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
                "rating_month": row[6], "rating_list_date": row[7],
            })
        except Exception:
            continue
    tournaments.sort(key=lambda x: x["start_date"])
    return {"count": len(tournaments), "tournaments": tournaments}


@app.get("/get_country_tournaments")
def get_country_tournaments(country: str = "BAN"):
    url = f"https://ratings.fide.com/a_tournaments.php?country={country}&_={int(time.time() * 1000)}"
    data = fetch_fide_json(url)
    tournaments = []
    today = datetime.now().date()
    for row in data.get("data", []):
        try:
            start_date = datetime.strptime(row[4], "%Y-%m-%d").date()
            end_date = datetime.strptime(row[5], "%Y-%m-%d").date() if row[5] else start_date
            if end_date < today:
                continue
            tournaments.append({
                "id": row[0], "name": row[1], "location": row[2],
                "start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
                "rating_month": row[6], "rating_list_date": row[7],
            })
        except Exception:
            continue
    tournaments.sort(key=lambda x: x["start_date"])
    return {"country": country, "count": len(tournaments), "country_tournaments": tournaments}
