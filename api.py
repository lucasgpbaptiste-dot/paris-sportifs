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
    "ligue1":   "FL1",
    "premier":  "PL",
    "laliga":   "PD",
    "seriea":   "SA",
    "bundesliga":"BL1",
}

@app.get("/")
def accueil():
    return {"status": "ok", "message": "API Paris Sportifs operationnelle"}

@app.get("/matchs-reels/{competition}")
def get_matchs_reels(competition: str):
    if not FOOTBALL_API_KEY:
        return {"erreur": "Clé API football manquante"}
    
    code = COMPETITIONS.get(competition.lower())
    if not code:
        return {"erreur": f"Compétition inconnue. Choisis parmi : {list(COMPETITIONS.keys())}"}
    
    try:
        headers = {"X-Auth-Token": FOOTBALL_API_KEY}
        res = requests.get(
            f"{FOOTBALL_API_URL}/competitions/{code}/matches?status=SCHEDULED",
            headers=headers
        )
        data = res.json()
        matchs = data.get("matches", [])[:5]
        
        resultats = []
        for m in matchs:
            team1 = m["homeTeam"]["name"]
            team2 = m["awayTeam"]["name"]
            date  = m["utcDate"][:10]
            
            analyse = MatchAnalysis(
                sport="foot",
                team1=team1,
                team2=team2,
                competition=m.get("competition", {}).get("name", competition),
            )
            d = analyse.to_dict()
            d["date"] = date
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