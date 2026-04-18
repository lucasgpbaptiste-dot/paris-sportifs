# -*- coding: utf-8 -*-
import os
import requests
from datetime import date
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sport_betting_analyzer import MatchAnalysis, BettingTicket, SAMPLE_MATCHES, SPORTS

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

FOOTBALL_API_KEY    = os.environ.get('FOOTBALL_API_KEY', '')
BALLDONTLIE_API_KEY = os.environ.get('BALLDONTLIE_API_KEY', '')
FOOTBALL_API_URL    = 'https://api.football-data.org/v4'
NBA_API_URL         = 'https://api.balldontlie.io/v1'

COMPETITIONS = {'ligue1':'FL1','premier':'PL','laliga':'PD','seriea':'SA','bundesliga':'BL1'}

def get_classement(code):
    try:
        headers = {'X-Auth-Token': FOOTBALL_API_KEY}
        res = requests.get(f'{FOOTBALL_API_URL}/competitions/{code}/standings', headers=headers)
        data = res.json()
        total = next((s for s in data.get('standings',[]) if s.get('type')=='TOTAL'), None)
        if not total: return {}
        classement = {}
        for entry in total.get('table',[]):
            nom = entry['team']['name']
            classement[nom] = {'position':entry['position'],'points':entry['points'],'joues':entry['playedGames'],'gagnes':entry['won'],'perdus':entry['lost'],'nuls':entry['draw'],'buts_pour':entry['goalsFor'],'buts_contre':entry['goalsAgainst']}
        return classement
    except Exception:
        return {}

def generer_combines(matchs_analyses, mise):
    combines = {}
    safe = [m for m in matchs_analyses if m['confidence'] >= 60][:3]
    if len(safe) >= 2:
        selections = []
        for m in safe:
            pari = next((b for b in m['bets'] if b['recommended']), min(m['bets'], key=lambda b: b['cote']))
            selections.append({'match':m['team1']+' vs '+m['team2'],'label':pari['label'],'cote':pari['cote'],'date':m.get('date','')})
        cote = round(eval('*'.join([str(s['cote']) for s in selections])),2)
        combines['safe'] = {'type':'safe','label':'Safe','description':'Paris prudents sur favoris clairs','selections':selections,'combined_cote':cote,'mise':mise,'potential_gain':round(cote*mise,2)}
    equilibre = [m for m in matchs_analyses if 40 <= m['confidence'] <= 70][:3]
    if len(equilibre) >= 2:
        selections = []
        for m in equilibre:
            pari = next((b for b in m['bets'] if b['recommended']), m['bets'][0])
            selections.append({'match':m['team1']+' vs '+m['team2'],'label':pari['label'],'cote':pari['cote'],'date':m.get('date','')})
        cote = round(eval('*'.join([str(s['cote']) for s in selections])),2)
        combines['equilibre'] = {'type':'equilibre','label':'Equilibre','description':'Bon rapport risque/gain','selections':selections,'combined_cote':cote,'mise':mise,'potential_gain':round(cote*mise,2)}
    risque = sorted(matchs_analyses, key=lambda m: max(b['cote'] for b in m['bets']), reverse=True)[:3]
    if len(risque) >= 2:
        selections = []
        for m in risque:
            pari = max(m['bets'], key=lambda b: b['cote'])
            selections.append({'match':m['team1']+' vs '+m['team2'],'label':pari['label'],'cote':pari['cote'],'date':m.get('date','')})
        cote = round(eval('*'.join([str(s['cote']) for s in selections])),2)
        combines['risque'] = {'type':'risque','label':'Risque','description':'Cotes elevees, gains maximaux','selections':selections,'combined_cote':cote,'mise':mise,'potential_gain':round(cote*mise,2)}
    return combines

@app.get('/')
def accueil():
    return {'status':'ok','message':'API Paris Sportifs operationnelle'}

@app.get('/matchs-reels/{competition}')
def get_matchs_reels(competition: str, mise: float = 10.0):
    if not FOOTBALL_API_KEY: return {'erreur':'Cle API football manquante'}
    code = COMPETITIONS.get(competition.lower())
    if not code: return {'erreur':'Competition inconnue'}
    try:
        headers = {'X-Auth-Token': FOOTBALL_API_KEY}
        res = requests.get(f'{FOOTBALL_API_URL}/competitions/{code}/matches?status=SCHEDULED', headers=headers)
        matchs = res.json().get('matches',[])[:6]
        classement = get_classement(code)
        matchs_analyses = []
        for m in matchs:
            team1 = m['homeTeam']['name']
            team2 = m['awayTeam']['name']
            date_match = m['utcDate'][:10]
            stats1 = classement.get(team1,{})
            stats2 = classement.get(team2,{})
            bilan1 = f"{stats1.get('gagnes',0)}-{stats1.get('perdus',0)}" if stats1 else ''
            bilan2 = f"{stats2.get('gagnes',0)}-{stats2.get('perdus',0)}" if stats2 else ''
            analyse = MatchAnalysis(sport='foot',team1=team1,team2=team2,competition=m.get('competition',{}).get('name',competition),record1=bilan1,record2=bilan2)
            d = analyse.to_dict()
            d['date'] = date_match
            if stats1: d['stats1'] = {'position':stats1['position'],'points':stats1['points'],'buts_pour':stats1['buts_pour']}
            if stats2: d['stats2'] = {'position':stats2['position'],'points':stats2['points'],'buts_pour':stats2['buts_pour']}
            matchs_analyses.append(d)
        return {'competition':competition,'matchs':matchs_analyses,'combines':generer_combines(matchs_analyses,mise)}
    except Exception as e:
        return {'erreur':str(e)}

@app.get('/nba')
def get_nba(mise: float = 10.0):
    if not BALLDONTLIE_API_KEY: return {'erreur':'Cle API NBA manquante'}
    try:
        headers = {'Authorization': BALLDONTLIE_API_KEY}
        today = date.today().isoformat()
        res = requests.get(f'{NBA_API_URL}/games?dates[]={today}&per_page=15&season=2024', headers=headers)
        if res.status_code != 200: return {'erreur':f'Erreur API NBA : {res.status_code}'}
        games = res.json().get('data',[])
        res2 = requests.get(f'{NBA_API_URL}/standings?season=2024', headers=headers)
        standings = {}
        if res2.status_code == 200:
            for s in res2.json().get('data',[]):
                nom = s['team']['full_name']
                standings[nom] = {'wins':s['wins'],'losses':s['losses'],'rank':s.get('conference_rank',0)}
        matchs_analyses = []
        for g in games:
            team1 = g['home_team']['full_name']
            team2 = g['visitor_team']['full_name']
            date_match = g['date'][:10]
            stats1 = standings.get(team1,{})
            stats2 = standings.get(team2,{})
            bilan1 = f"{stats1.get('wins',0)}-{stats1.get('losses',0)}" if stats1 else ''
            bilan2 = f"{stats2.get('wins',0)}-{stats2.get('losses',0)}" if stats2 else ''
            analyse = MatchAnalysis(sport='nba',team1=team1,team2=team2,competition='NBA',record1=bilan1,record2=bilan2)
            d = analyse.to_dict()
            d['date'] = date_match
            if stats1: d['stats1'] = {'wins':stats1['wins'],'losses':stats1['losses'],'rank':stats1['rank']}
            if stats2: d['stats2'] = {'wins':stats2['wins'],'losses':stats2['losses'],'rank':stats2['rank']}
            matchs_analyses.append(d)
        if not matchs_analyses: return {'sport':'nba','matchs':[],'combines':{},'message':f'Aucun match NBA le {today}'}
        return {'sport':'nba','matchs':matchs_analyses,'combines':generer_combines(matchs_analyses,mise)}
    except Exception as e:
        return {'erreur':str(e)}

@app.get('/matchs/{sport}')
def get_matchs(sport: str):
    if sport not in SAMPLE_MATCHES: return {'erreur':'Sport inconnu'}
    resultats = []
    for m in SAMPLE_MATCHES[sport]:
        analyse = MatchAnalysis(sport=sport,team1=m['team1'],team2=m['team2'],competition=m['competition'],record1=m.get('record1',''),record2=m.get('record2',''),forme1=m.get('forme1',''),forme2=m.get('forme2',''))
        resultats.append(analyse.to_dict())
    return {'sport':sport,'matchs':resultats}

@app.get('/ticket/{sport}')
def get_ticket(sport: str, mise: float = 10.0):
    if sport not in SAMPLE_MATCHES: return {'erreur':'Sport inconnu'}
    ticket = BettingTicket()
    for m in SAMPLE_MATCHES[sport]:
        analyse = MatchAnalysis(sport=sport,team1=m['team1'],team2=m['team2'],competition=m['competition'],record1=m.get('record1',''),record2=m.get('record2',''))
        ticket.add_best(analyse)
    return ticket.export_json(mise)
