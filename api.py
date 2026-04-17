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
    "ligue1":     "FL1",
    "premier":    "PL",
    "laliga":     "PD",
    "seriea":     "SA",
    "bundesliga": "BL1",
}

def get_classement(code):
    try:
        headers = {"X-Auth-Token": FOOTBALL_API_KEY}
        res = requests.get(f"{FOOTBALL_API_URL}/competitions/{code}/standings", headers=headers)
        data = res.json()
        standings = data.get("standings", [])
        total = next((s for s in standings if s.get("type") == "TOTAL"), None)
        if not total:
            return {}
        classement = {}
        for entry in total.get("table", []):
            nom = entry["team"]["name"]
            classement[nom] = {
                "position":     entry["position"],
                "points":       entry["points"],
                "joues":        entry["playedGames"],
                "gagnes":       entry["won"],
                "perdus":       entry["lost"],
                "nuls":         entry["draw"],
                "buts_pour":    entry["goalsFor"],
                "buts_contre":  entry["goalsAgainst"],
            }
        return classement
    except Exception:
        return {}

def get_forme(team_id, headers):
    try:
        res = requests.get(f"{FOOTBALL_API_URL}/teams/{team_id}/matches?status=FINISHED&limit=5", headers=headers)
        data = res.json()
        matchs = data.get("matches", [])
        forme = []
        for m in matchs:
            home = m["homeTeam"]["id"] == team_id
            score_home = m["score"]["fullTime"]["home"] or 0
            score_away = m["score"]["fullTime"]["away"] or 0
            if home:
                forme.append("V" if score_home > score_away else "D" if score_home < score_away else "N")
            else:
                forme.append("V" if score_away > score_home else "D" if score_away < score_home else "N")
        return forme
    except Exception:
        return []

def calculer_score_forme(forme):
    if not forme:
        return 50
    points = {"V": 3, "N": 1, "D": 0}
    total = sum(points.get(r, 0) for r in forme)
    return round(total / (len(forme) * 3) * 100)

def generer_combines(matchs_analyses, mise):
    combines = {}

    # SAFE : matchs avec confiance >= 60, paris les plus surs
    safe = [m for m in matchs_analyses if m["confidence"] >= 60][:3]
    if len(safe) >= 2:
        selections_safe = []
        for m in safe:
            pari = next((b for b in m["bets"] if b["id"] == "winner_1" and b["recommended"]),
                       min(m["bets"], key=lambda b: b["cote"]))
            selections_safe.append({
                "match": m["team1"] + " vs " + m["team2"],
                "label": pari["label"],
                "cote":  pari["cote"],
                "date":  m.get("date", ""),
            })
        cote_safe = round(eval("*".join([str(s["cote"]) for s in selections_safe])), 2)
        combines["safe"] = {
            "type": "safe",
            "label": "Safe",
            "description": "Paris prudents sur favoris clairs",
            "selections": selections_safe,
            "combined_cote": cote_safe,
            "mise": mise,
            "potential_gain": round(cote_safe * mise, 2),
        }

    # EQUILIBRE : matchs avec confiance entre 45-65, paris equilibres
    equilibre = [m for m in matchs_analyses if 40 <= m["confidence"] <= 70][:3]
    if len(equilibre) >= 2:
        selections_eq = []
        for m in equilibre:
            pari = next((b for b in m["bets"] if b["recommended"]),
                       m["bets"][2] if len(m["bets"]) > 2 else m["bets"][0])
            selections_eq.append({
                "match": m["team1"] + " vs " + m["team2"],
                "label": pari["label"],
                "cote":  pari["cote"],
                "date":  m.get("date", ""),
            })
        cote_eq = round(eval("*".join([str(s["cote"]) for s in selections_eq])), 2)
        combines["equilibre"] = {
            "type": "equilibre",
            "label": "Equilibre",
            "description": "Bon rapport risque/gain",
            "selections": selections_eq,
            "combined_cote": cote_eq,
            "mise": mise,
            "potential_gain": round(cote_eq * mise, 2),
        }

    # RISQUE : matchs avec bonnes cotes, paris audacieux
    risque = sorted(matchs_analyses, key=lambda m: max(b["cote"] for b in m["bets"]), reverse=True)[:3]
    if len(risque) >= 2:
        selections_r = []
        for m in risque:
            pari = max(m["bets"], key=lambda b: b["cote"])
            selections_r.append({
                "match": m["team1"] + " vs " + m["team2"],
                "label": pari["label"],
                "cote":  pari["cote"],
                "date":  m.get("date", ""),
            })
        cote_r = round(eval("*".join([str(s["cote"]) for s in selections_r])), 2)
        combines["risque"] = {
            "type": "risque",
            "label": "Risque",
            "description": "Cotes elevees, gains maximaux",
            "selections": selections_r,
            "combined_cote": cote_r,
            "mise": mise,
            "potential_gain": round(cote_r * mise, 2),
        }

    return combines

@app.get("/")
def accueil():
    return {"status": "ok", "message": "API Paris Sportifs operationnelle"}

@app.get("/matchs-reels/{competition}")
def get_matchs_reels(competition: str, mise: float = 10.0):
    if not FOOTBALL_API_KEY:
        return {"erreur": "Cle API football manquante"}
    code = COMPETITIONS.get(competition.lower())
    if not code:
        return {"erreur": f"Competition inconnue"}
    try:
        headers = {"X-Auth-Token": FOOTBALL_API_KEY}
        res = requests.get(f"{FOOTBALL_API_URL}/competitions/{code}/matches?status=SCHEDULED", headers=headers)
        data = res.json()
        matchs = data.get("matches", [])[:6]
        classement = get_classement(code)

        matchs_analyses = []
        for m in matchs:
            team1 = m["homeTeam"]["name"]
            team2 = m["awayTeam"]["name"]
            date  = m["utcDate"][:10]
            stats1 = classement.get(team1, {})
            stats2 = classement.get(team2, {})
            bilan1 = f"{stats1.get('gagnes',0)}-{stats1.get('perdus',0)}" if stats1 else ""
            bilan2 = f"{stats2.get('gagnes',0)}-{stats2.get('perdus',0)}" if stats2 else ""

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
            if stats1:
                d["stats1"] = {"position": stats1["position"], "points": stats1["points"], "buts_pour": stats1["buts_pour"]}
            if stats2:
                d["stats2"] = {"position": stats2["position"], "points": stats2["points"], "buts_pour": stats2["buts_pour"]}
            matchs_analyses.append(d)

        combines = generer_combines(matchs_analyses, mise)
        return {"competition": competition, "matchs": matchs_analyses, "combines": combines}

    except Exception as e:
        return {"erreur": str(e)}

@app.get("/matchs/{sport}")
def get_matchs(sport: str):
    if sport not in SAMPLE_MATCHES:
        return {"erreur": f"Sport inconnu"}
    resultats = []
    for m in SAMPLE_MATCHES[sport]:
        analyse = MatchAnalysis(sport=sport, team1=m["team1"], team2=m["team2"],
            competition=m["competition"], record1=m.get("record1",""), record2=m.get("record2",""),
            forme1=m.get("forme1",""), forme2=m.get("forme2",""))
        resultats.append(analyse.to_dict())
    return {"sport": sport, "matchs": resultats}

@app.get("/ticket/{sport}")
def get_ticket(sport: str, mise: float = 10.0):
    if sport not in SAMPLE_MATCHES:
        return {"erreur": f"Sport inconnu"}
    ticket = BettingTicket()
    for m in SAMPLE_MATCHES[sport]:
        analyse = MatchAnalysis(sport=sport, team1=m["team1"], team2=m["team2"],
            competition=m["competition"], record1=m.get("record1",""), record2=m.get("record2",""))
        ticket.add_best(analyse)
    return ticket.export_json(mise)