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

@app.get("/")
def accueil():
    return {"status": "ok", "message": "API Paris Sportifs opérationnelle"}

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