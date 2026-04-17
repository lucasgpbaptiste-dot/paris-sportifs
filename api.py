# -*- coding: utf-8 -*-
import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sport_betting_analyzer import MatchAnalysis, BettingTicket, SAMPLE_MATCHES, SPORTS

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY", "")
FOOTBALL_API_URL = "https://api.football-data.org/v4"

COMPETITIONS = {
    "ligue1":      "FL1",
    "premier":     "PL",
    "laliga":      "PD",
    "seriea":      "SA",
    "bundesliga":  "BL1",
}

def get_classement(code: str) -> dict:
    """Recupere le classement de la competition et retourne un dict {nom_equipe: {position, points, joues, gagnes, perdus}}"""
    try:
        headers = {"X-Auth-Token": FOOTBALL_API_KEY}
        res = requests.get(
            f"{FOOTBALL_API_URL}/competitions/{code}/standings",
            headers=headers
        )
        data = res.json()
        standings = data.get("standings", [])
        total = next((s for s in standings if s.get("type") == "TOTAL"), None)
        if not total:
            return {}
        classement = {}
        for entry in total.get("table", []):
            nom = entry["team"]["name"]
            classement[nom] = {
                "position": entry["position"],
                "points":   entry["points"],
                "joues":    entry["playedGames"],
                "gagnes":   entry["won"],
                "perdus":   entry["lost"],
                "nuls":     entry["draw"],
                "buts_pour":    entry["goalsFor"],
                "buts_contre":  entry["goalsAgainst"],
            }
        return classement
    except Exception:
        return {}

def bilan_depuis_stats(stats: dict) -> str:
    if not stats:
        return ""
    return f"{stats['gagnes']}-{stats['perdus']}"

def confiance_depuis_stats(stats1: dict, stats2: dict) -> int:
    if not stats1 or not stats2:
        return 50
    diff_position = stats2["position"] - stats1["position"]
    diff_points   = stats1["points"] - stats2["points"]
    conf = 50 + diff_position * 2 + diff_points * 0.5
    return int(min(85, max(20, round(conf))))

@app.get("/")
def accueil():
    return {"status": "ok", "message": "API Paris Sportifs operationnelle"}

@app.get("/matchs-reels/{competition}")
def get_matchs_reels(competition: str):
    if not FOOTBALL_API_KEY:
        return {"erreur": "Cle API football manquante"}

    code = COMPETITIONS.get(competition.lower())
    if not code:
        return {"erreur": f"Competition inconnue. Choisis parmi : {list(COMPETITIONS.keys())}"}

    try:
        headers = {"X-Auth-Token": FOOTBALL_API_KEY}

        # Recupere les matchs
        res = requests.get(
            f"{FOOTBALL_API_URL}/competitions/{code}/matches?status=SCHEDULED",
            headers=headers
        )
        data = res.json()
        matchs = data.get("matches", [])[:5]

        # Recupere le classement
        classement = get_classement(code)

        resultats = []
        for m in matchs:
            team1 = m["homeTeam"]["name"]
            team2 = m["awayTeam"]["name"]
            date  = m["utcDate"][:10]

            stats1 = classement.get(team1, {})
            stats2 = classement.get(team2, {})

            bilan1 = bilan_depuis_stats(stats1)
            bilan2 = bilan_depuis_stats(stats2)

            analyse = MatchAnalysis(
                sport="foot",
                team1=team1,
                team2=team2,
                competition=m.get("competition", {}).get("name", competition),
                record1=bilan1,
                record2=bilan2,
            )

            d = analyse.to_dict()
            d["date"] = date

            # Ajoute les vraies stats
            if stats1:
                d["stats1"] = {
                    "position": stats1["position"],
                    "points":   stats1["points"],
                    "buts_pour": stats1["buts_pour"],
                    "buts_contre": stats1["buts_contre"],
                }
            if stats2:
                d["stats2"] = {
                    "position": stats2["position"],
                    "points":   stats2["points"],
                    "buts_pour": stats2["buts_pour"],
                    "buts_contre": stats2["buts_contre"],
                }

            resultats.append(d)

        return {"competition": competition, "matchs": resultats}

    except Exception as e:
        return {"erreur": str(e)}

@app.get("/matchs/{sport}")
def get_matchs(sport: str):
    if sport not in SAMPLE_MATCHES:
        return {"erreur": f"Sport inconnu. Choisis parmi : {SPORTS}"}
    resultats = []
    for m in SAMPLE_MATCHES[sport]:
        analyse = MatchAnalysis(
            sport=sport,
            team1=m["team1"],
            team2=m["team2"],
            competition=m["competition"],
            record1=m.get("record1", ""),
            record2=m.get("record2", ""),
            forme1=m.get("forme1", ""),
            forme2=m.get("forme2", ""),
        )
        resultats.append(analyse.to_dict())
    return {"sport": sport, "matchs": resultats}

@app.get("/ticket/{sport}")
def get_ticket(sport: str, mise: float = 10.0):
    if sport not in SAMPLE_MATCHES:
        return {"erreur": f"Sport inconnu. Choisis parmi : {SPORTS}"}
    ticket = BettingTicket()
    for m in SAMPLE_MATCHES[sport]:
        analyse = MatchAnalysis(
            sport=sport,
            team1=m["team1"],
            team2=m["team2"],
            competition=m["competition"],
            record1=m.get("record1", ""),
            record2=m.get("record2", ""),
            forme1=m.get("forme1", ""),
            forme2=m.get("forme2", ""),
        )
        ticket.add_best(analyse)
    return ticket.export_json(mise)