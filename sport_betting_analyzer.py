"""
=============================================================
  Sport Betting Analyzer — NBA / Football / Tennis
  Analyse automatique et génération de tickets combinés
=============================================================

INSTALLATION :
    pip install requests anthropic colorama tabulate

UTILISATION :
    # Mode interactif (saisie manuelle d'un match)
    python sport_betting_analyzer.py --mode manuel

    # Mode automatique (meilleurs matchs du jour via API)
    python sport_betting_analyzer.py --mode auto --sport nba
    python sport_betting_analyzer.py --mode auto --sport foot
    python sport_betting_analyzer.py --mode auto --sport tennis
    python sport_betting_analyzer.py --mode auto --sport all

    # Analyse directe d'un match
    python sport_betting_analyzer.py --match "PSG vs OM" --sport foot --bilan1 "18-5" --bilan2 "14-9"

CLÉS API NÉCESSAIRES :
    - ANTHROPIC_API_KEY  : pour l'analyse IA des matchs
    - SPORTRADAR_API_KEY : (optionnel) pour les données en temps réel
      Sans cette clé, le script fonctionne avec des données simulées.

=============================================================
"""

import os
import sys
import json
import time
import random
import argparse
from datetime import datetime
from typing import Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    class Fore:
        GREEN = YELLOW = RED = BLUE = CYAN = MAGENTA = WHITE = RESET = ""
    class Style:
        BRIGHT = RESET_ALL = DIM = ""

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


# =============================================================
#  CONFIGURATION
# =============================================================

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SPORTRADAR_API_KEY = os.environ.get("SPORTRADAR_API_KEY", "")

SPORTS = ["nba", "foot", "tennis"]

BET_TYPES = {
    "nba": [
        {"id": "winner_1",  "label": "Victoire équipe 1",        "base_cote": 1.75},
        {"id": "winner_2",  "label": "Victoire équipe 2",        "base_cote": 2.10},
        {"id": "over",      "label": "Over total de points",     "base_cote": 1.85},
        {"id": "under",     "label": "Under total de points",    "base_cote": 1.85},
        {"id": "handicap",  "label": "Handicap -5.5 favori",     "base_cote": 1.90},
    ],
    "foot": [
        {"id": "winner_1",  "label": "Victoire équipe 1",        "base_cote": 1.80},
        {"id": "draw",      "label": "Match nul",                "base_cote": 3.20},
        {"id": "winner_2",  "label": "Victoire équipe 2",        "base_cote": 2.40},
        {"id": "btts",      "label": "Les deux équipes marquent","base_cote": 1.70},
        {"id": "over25",    "label": "Over 2.5 buts",            "base_cote": 1.75},
        {"id": "under25",   "label": "Under 2.5 buts",          "base_cote": 2.00},
    ],
    "tennis": [
        {"id": "winner_1",  "label": "Victoire joueur 1",        "base_cote": 1.65},
        {"id": "winner_2",  "label": "Victoire joueur 2",        "base_cote": 2.20},
        {"id": "2sets",     "label": "En 2 sets",                "base_cote": 2.10},
        {"id": "3sets",     "label": "En 3 sets",                "base_cote": 1.80},
        {"id": "overjeux",  "label": "Over 21.5 jeux",           "base_cote": 1.85},
    ],
}

SAMPLE_MATCHES = {
    "nba": [
        {"team1": "Boston Celtics",    "team2": "Miami Heat",        "competition": "NBA — Eastern", "record1": "56-26", "record2": "43-39", "forme1": "VVDVV", "forme2": "DVDVD"},
        {"team1": "Oklahoma City Thunder","team2": "Denver Nuggets", "competition": "NBA — Western","record1": "64-18", "record2": "54-28", "forme1": "VVVVD", "forme2": "VVDVV"},
        {"team1": "LA Lakers",         "team2": "Phoenix Suns",      "competition": "NBA — Western","record1": "53-29", "record2": "45-37", "forme1": "VDVVV", "forme2": "VVDVD"},
    ],
    "foot": [
        {"team1": "Paris Saint-Germain","team2": "Olympique Lyonnais","competition": "Ligue 1","record1": "22-4",  "record2": "15-11", "forme1": "VVVDV", "forme2": "DVVDV"},
        {"team1": "Real Madrid",        "team2": "FC Barcelona",     "competition": "La Liga",   "record1": "20-6",  "record2": "19-7",  "forme1": "VVDVV", "forme2": "VVVDV"},
        {"team1": "Arsenal",            "team2": "Manchester City",  "competition": "Premier League","record1":"18-8","record2": "21-5",  "forme1": "VDVVD", "forme2": "VVVVD"},
    ],
    "tennis": [
        {"team1": "Carlos Alcaraz",    "team2": "Novak Djokovic",    "competition": "Roland Garros QF","record1": "42-8", "record2": "38-12","forme1": "VVVDV", "forme2": "VDVVV"},
        {"team1": "Aryna Sabalenka",   "team2": "Iga Swiatek",       "competition": "Roland Garros SF","record1": "38-10","record2": "40-8", "forme1": "VVVVD", "forme2": "VVDVV"},
    ],
}


# =============================================================
#  UTILITAIRES
# =============================================================

def cprint(text, color="", bright=False, end="\n"):
    prefix = (Style.BRIGHT if bright else "") + color if HAS_COLOR else ""
    suffix = Style.RESET_ALL if HAS_COLOR else ""
    print(f"{prefix}{text}{suffix}", end=end)

def separator(char="─", width=60, color=Fore.WHITE):
    cprint(char * width, color)

def parse_record(record: str) -> dict:
    """Convertit '18-5' en dict {w, l, pct}."""
    if not record:
        return {"w": 0, "l": 0, "pct": 50}
    try:
        parts = record.strip().split("-")
        w, l = int(parts[0]), int(parts[1])
        pct = round(w / (w + l) * 100) if (w + l) > 0 else 50
        return {"w": w, "l": l, "pct": pct}
    except Exception:
        return {"w": 0, "l": 0, "pct": 50}

def parse_forme(forme: str) -> int:
    """Calcule le % de victoires sur la forme récente (ex: 'VVDVV')."""
    if not forme:
        return 50
    clean = forme.strip().upper().replace(" ", "")
    wins = clean.count("V")
    total = len([c for c in clean if c in ("V", "D")])
    return round(wins / total * 100) if total > 0 else 50

def compute_confidence(rec1: dict, rec2: dict, forme1: int, forme2: int) -> int:
    """Score de confiance 0-100 pour l'équipe 1."""
    diff_record = rec1["pct"] - rec2["pct"]
    diff_forme  = forme1 - forme2
    conf = 50 + diff_record * 0.3 + diff_forme * 0.15
    return int(min(85, max(20, round(conf))))

def estimate_cote(base: float, confidence: int, is_favorite: bool) -> float:
    """Ajuste la cote de base selon la confiance."""
    if is_favorite:
        factor = 0.92 if confidence > 60 else 1.05 if confidence < 40 else 1.0
    else:
        factor = 1.10 if confidence > 60 else 0.95 if confidence < 40 else 1.0
    jitter = random.uniform(0.97, 1.03)
    return round(base * factor * jitter, 2)


# =============================================================
#  ANALYSE D'UN MATCH
# =============================================================

class MatchAnalysis:
    def __init__(self, sport: str, team1: str, team2: str,
                 competition: str = "",
                 record1: str = "", record2: str = "",
                 forme1: str = "", forme2: str = ""):
        self.sport = sport
        self.team1 = team1
        self.team2 = team2
        self.competition = competition or sport.upper()
        self.rec1 = parse_record(record1)
        self.rec2 = parse_record(record2)
        self.forme1_pct = parse_forme(forme1)
        self.forme2_pct = parse_forme(forme2)
        self.confidence = compute_confidence(self.rec1, self.rec2, self.forme1_pct, self.forme2_pct)
        self.bets = self._generate_bets()

    def _generate_bets(self) -> list:
        templates = BET_TYPES.get(self.sport, BET_TYPES["foot"])
        bets = []
        for t in templates:
            is_fav = t["id"] == "winner_1"
            cote = estimate_cote(t["base_cote"], self.confidence, is_fav)
            bets.append({
                "id":    t["id"],
                "label": t["label"],
                "cote":  cote,
                "recommended": self._is_recommended(t["id"]),
            })
        return bets

    def _is_recommended(self, bet_id: str) -> bool:
        if bet_id == "winner_1" and self.confidence >= 60:
            return True
        if bet_id == "winner_2" and self.confidence <= 40:
            return True
        if bet_id in ("over", "over25", "btts") and self.forme1_pct + self.forme2_pct > 120:
            return True
        return False

    @property
    def favorite(self) -> str:
        if self.confidence >= 55:
            return self.team1
        elif self.confidence <= 45:
            return self.team2
        return "Équilibré"

    def display(self):
        separator("═", color=Fore.BLUE)
        cprint(f"  {self.competition} — {self.sport.upper()}", Fore.CYAN)
        cprint(f"  {self.team1}  vs  {self.team2}", Fore.WHITE, bright=True)
        separator("─", color=Fore.BLUE)

        if self.rec1["w"] + self.rec1["l"] > 0:
            print(f"  {self.team1:<28} Bilan : {self.rec1['w']}-{self.rec1['l']}  ({self.rec1['pct']}%)")
            print(f"  {self.team2:<28} Bilan : {self.rec2['w']}-{self.rec2['l']}  ({self.rec2['pct']}%)")
            print()

        conf_color = Fore.GREEN if self.confidence >= 60 else Fore.YELLOW if self.confidence >= 45 else Fore.RED
        cprint(f"  Favori estimé   : {self.favorite}", Fore.WHITE)
        cprint(f"  Confiance       : {self.confidence}%", conf_color, bright=True)
        print()

        cprint("  Paris disponibles :", Fore.CYAN)
        rows = []
        for b in self.bets:
            rec = "★ RECOMMANDÉ" if b["recommended"] else ""
            rows.append([b["label"], f"{b['cote']:.2f}", rec])

        if HAS_TABULATE:
            print(tabulate(rows, headers=["Type de pari", "Cote", ""], tablefmt="simple", colalign=("left","center","left")))
        else:
            for r in rows:
                marker = f"  {Fore.GREEN}[★]{Style.RESET_ALL}" if r[2] else "   [ ]"
                print(f"{marker}  {r[0]:<38} cote {r[1]}")
        separator("═", color=Fore.BLUE)

    def to_dict(self) -> dict:
        return {
            "sport": self.sport,
            "competition": self.competition,
            "team1": self.team1,
            "team2": self.team2,
            "record1": f"{self.rec1['w']}-{self.rec1['l']}",
            "record2": f"{self.rec2['w']}-{self.rec2['l']}",
            "confidence": self.confidence,
            "favorite": self.favorite,
            "bets": self.bets,
        }


# =============================================================
#  TICKET COMBINÉ
# =============================================================

class BettingTicket:
    def __init__(self):
        self.selections: list[dict] = []

    def add(self, match: MatchAnalysis, bet_id: str):
        """Ajoute la meilleure sélection d'un match."""
        bet = next((b for b in match.bets if b["id"] == bet_id), None)
        if not bet:
            bet = max(match.bets, key=lambda b: 1 if b["recommended"] else 0)
        self.selections.append({
            "match":       f"{match.team1} vs {match.team2}",
            "competition": match.competition,
            "sport":       match.sport,
            "label":       bet["label"],
            "cote":        bet["cote"],
        })

    def add_best(self, match: MatchAnalysis):
        """Ajoute automatiquement le pari le plus recommandé."""
        recommended = [b for b in match.bets if b["recommended"]]
        if recommended:
            best = max(recommended, key=lambda b: b["cote"])
        else:
            best = match.bets[0]
        self.selections.append({
            "match":       f"{match.team1} vs {match.team2}",
            "competition": match.competition,
            "sport":       match.sport,
            "label":       best["label"],
            "cote":        best["cote"],
        })

    @property
    def combined_cote(self) -> float:
        cote = 1.0
        for s in self.selections:
            cote *= s["cote"]
        return round(cote, 2)

    def potential_gain(self, mise: float) -> float:
        return round(mise * self.combined_cote, 2)

    def display(self, mise: float = 10.0):
        print()
        separator("═", 60, Fore.YELLOW)
        cprint("  TICKET COMBINÉ", Fore.YELLOW, bright=True)
        cprint(f"  Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", Fore.WHITE)
        separator("─", 60, Fore.YELLOW)

        for i, s in enumerate(self.selections, 1):
            cprint(f"  Sélection {i} — {s['sport'].upper()}", Fore.CYAN)
            print(f"  {s['competition']}")
            cprint(f"  {s['match']}", Fore.WHITE, bright=True)
            print(f"  Pari    : {s['label']}")
            cprint(f"  Cote    : {s['cote']:.2f}", Fore.BLUE, bright=True)
            separator("·", 40, Fore.WHITE)

        print()
        cprint(f"  Nb sélections  : {len(self.selections)}", Fore.WHITE)
        cprint(f"  Cote combinée  : {self.combined_cote:.2f}", Fore.BLUE, bright=True)
        cprint(f"  Mise           : {mise:.2f} €", Fore.WHITE)
        cprint(f"  Gain potentiel : {self.potential_gain(mise):.2f} €", Fore.GREEN, bright=True)
        separator("═", 60, Fore.YELLOW)
        cprint("\n  ⚠  Jeu responsable — les paris comportent des risques financiers.", Fore.RED)
        print()

    def export_json(self, mise: float = 10.0) -> dict:
        return {
            "date": datetime.now().isoformat(),
            "selections": self.selections,
            "combined_cote": self.combined_cote,
            "mise": mise,
            "potential_gain": self.potential_gain(mise),
        }


# =============================================================
#  ANALYSE IA VIA ANTHROPIC (optionnel)
# =============================================================

def ai_analyze(match: MatchAnalysis) -> Optional[str]:
    """Envoie les données du match à Claude pour une analyse approfondie."""
    if not HAS_ANTHROPIC or not ANTHROPIC_API_KEY:
        return None
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = f"""Tu es un analyste sportif expert. Analyse ce match et donne :
1. Ton pronostic principal (vainqueur ou pari le plus probable)
2. Le niveau de risque (faible / moyen / élevé)
3. Un argument clé en 1-2 phrases
4. Le meilleur pari parmi : {[b['label'] for b in match.bets]}

Match : {match.team1} vs {match.team2}
Sport : {match.sport.upper()}
Compétition : {match.competition}
Bilan {match.team1} : {match.rec1['w']}-{match.rec1['l']} ({match.rec1['pct']}% victoires)
Bilan {match.team2} : {match.rec2['w']}-{match.rec2['l']} ({match.rec2['pct']}% victoires)
Forme récente {match.team1} : {match.forme1_pct}% victoires
Forme récente {match.team2} : {match.forme2_pct}% victoires

Réponds en JSON avec les clés : pronostic, risque, argument, meilleur_pari"""

        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text
    except Exception as e:
        return f"Erreur API : {e}"


# =============================================================
#  MODES D'EXÉCUTION
# =============================================================

def mode_manuel():
    """Mode interactif : l'utilisateur saisit les infos du match."""
    cprint("\n=== SPORT BETTING ANALYZER — Mode manuel ===\n", Fore.CYAN, bright=True)

    sport = input(f"Sport [{'/'.join(SPORTS)}] : ").strip().lower()
    if sport not in SPORTS:
        sport = "foot"

    competition = input("Compétition (ex: Ligue 1) : ").strip() or sport.upper()
    team1 = input("Équipe / Joueur 1 : ").strip()
    team2 = input("Équipe / Joueur 2 : ").strip()
    if not team1 or not team2:
        cprint("Erreur : renseignez les deux équipes.", Fore.RED)
        return

    record1 = input(f"Bilan {team1} (ex: 18-5, optionnel) : ").strip()
    record2 = input(f"Bilan {team2} (ex: 14-9, optionnel) : ").strip()
    forme1  = input(f"Forme récente {team1} (ex: VVDVV, optionnel) : ").strip()
    forme2  = input(f"Forme récente {team2} (ex: DVDVV, optionnel) : ").strip()

    match = MatchAnalysis(sport, team1, team2, competition, record1, record2, forme1, forme2)
    match.display()

    if ANTHROPIC_API_KEY:
        cprint("\nAnalyse IA en cours...", Fore.YELLOW)
        ai_result = ai_analyze(match)
        if ai_result:
            cprint("\n--- Analyse Claude ---", Fore.MAGENTA, bright=True)
            print(ai_result)

    add = input("\nAjouter au ticket combiné ? [o/n] : ").strip().lower()
    if add == "o":
        ticket = BettingTicket()
        ticket.add_best(match)

        while True:
            another = input("Ajouter un autre match ? [o/n] : ").strip().lower()
            if another != "o":
                break
            t1 = input("Équipe / Joueur 1 : ").strip()
            t2 = input("Équipe / Joueur 2 : ").strip()
            sp = input(f"Sport [{'/'.join(SPORTS)}] : ").strip().lower()
            if sp not in SPORTS:
                sp = sport
            r1 = input(f"Bilan {t1} : ").strip()
            r2 = input(f"Bilan {t2} : ").strip()
            m = MatchAnalysis(sp, t1, t2, sp.upper(), r1, r2)
            m.display()
            ticket.add_best(m)

        try:
            mise = float(input("Mise (€) [défaut: 10] : ").strip() or "10")
        except ValueError:
            mise = 10.0

        ticket.display(mise)

        save = input("Sauvegarder le ticket en JSON ? [o/n] : ").strip().lower()
        if save == "o":
            filename = f"ticket_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(ticket.export_json(mise), f, ensure_ascii=False, indent=2)
            cprint(f"Ticket sauvegardé : {filename}", Fore.GREEN)


def mode_auto(sports_filter: list = None):
    """Mode automatique : analyse les meilleurs matchs du jour (données simulées)."""
    cprint("\n=== SPORT BETTING ANALYZER — Mode automatique ===\n", Fore.CYAN, bright=True)
    cprint("Récupération des matchs du jour...", Fore.YELLOW)
    time.sleep(0.5)

    if not sports_filter:
        sports_filter = SPORTS

    all_matches = []
    for sport in sports_filter:
        if sport in SAMPLE_MATCHES:
            for m in SAMPLE_MATCHES[sport]:
                all_matches.append((sport, m))

    if not all_matches:
        cprint("Aucun match trouvé.", Fore.RED)
        return

    ticket = BettingTicket()
    analyses = []

    for sport, m in all_matches:
        analysis = MatchAnalysis(
            sport=sport,
            team1=m["team1"],
            team2=m["team2"],
            competition=m["competition"],
            record1=m.get("record1", ""),
            record2=m.get("record2", ""),
            forme1=m.get("forme1", ""),
            forme2=m.get("forme2", ""),
        )
        analyses.append(analysis)
        analysis.display()

    cprint("\nSélection automatique des meilleurs paris...", Fore.YELLOW)
    time.sleep(0.3)

    best = sorted(analyses, key=lambda a: a.confidence, reverse=True)[:3]
    for a in best:
        ticket.add_best(a)

    try:
        mise = float(input("\nMise (€) [défaut: 10] : ").strip() or "10")
    except ValueError:
        mise = 10.0

    ticket.display(mise)

    save = input("Sauvegarder le ticket en JSON ? [o/n] : ").strip().lower()
    if save == "o":
        filename = f"ticket_auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(ticket.export_json(mise), f, ensure_ascii=False, indent=2)
        cprint(f"Ticket sauvegardé : {filename}", Fore.GREEN)


def mode_direct(match_str, sport, record1, record2, forme1="", forme2=""):
    """Analyse directe depuis les arguments CLI."""
    parts = match_str.split(" vs ")
    if len(parts) != 2:
        cprint("Format du match invalide. Utilisez : 'Équipe1 vs Équipe2'", Fore.RED)
        return
    team1, team2 = [p.strip() for p in parts]
    match = MatchAnalysis(sport, team1, team2, sport.upper(), record1, record2, forme1, forme2)
    match.display()

    ticket = BettingTicket()
    ticket.add_best(match)

    try:
        mise = float(input("\nMise (€) [défaut: 10] : ").strip() or "10")
    except ValueError:
        mise = 10.0
    ticket.display(mise)


# =============================================================
#  POINT D'ENTRÉE
# =============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Sport Betting Analyzer — NBA / Football / Tennis"
    )
    parser.add_argument("--mode",   choices=["manuel", "auto"], default="manuel",
                        help="Mode d'exécution (défaut: manuel)")
    parser.add_argument("--sport",  default="all",
                        help="Sport : nba / foot / tennis / all (défaut: all)")
    parser.add_argument("--match",  default="",
                        help="Match direct : 'Équipe1 vs Équipe2'")
    parser.add_argument("--bilan1", default="", help="Bilan équipe 1 (ex: 18-5)")
    parser.add_argument("--bilan2", default="", help="Bilan équipe 2 (ex: 14-9)")
    parser.add_argument("--forme1", default="", help="Forme récente équipe 1 (ex: VVDVV)")
    parser.add_argument("--forme2", default="", help="Forme récente équipe 2 (ex: DVDVV)")

    args = parser.parse_args()

    if args.match:
        sport = args.sport if args.sport in SPORTS else "foot"
        mode_direct(args.match, sport, args.bilan1, args.bilan2, args.forme1, args.forme2)
    elif args.mode == "auto":
        sports = SPORTS if args.sport == "all" else [args.sport]
        mode_auto(sports)
    else:
        mode_manuel()


if __name__ == "__main__":
    main()
