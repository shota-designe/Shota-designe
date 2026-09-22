"""
ReplyWise - Notification basique

Ce script ne fait aucun envoi réel (pas de vraie boîte mail, pas de vrai
Slack/Trustpilot). Il se contente de rendre visible, simplement, qu'il y a
des brouillons en attente de validation :
- affichage clair dans le terminal
- écriture d'un fichier a_approuver.txt facile à relire

Pensé pour être branché plus tard sur un vrai canal de notification
(email interne, Slack, etc.) sans changer le reste du pipeline.
"""

import json
from pathlib import Path

DOSSIER = Path(__file__).parent
FICHIER_QUEUE = DOSSIER / "pending_queue.json"
FICHIER_A_APPROUVER = DOSSIER / "a_approuver.txt"


def charger_file_attente():
    if not FICHIER_QUEUE.exists():
        return []
    with open(FICHIER_QUEUE, "r", encoding="utf-8") as f:
        return json.load(f)


def formater_entree(entree, numero):
    escalade = entree.get("escalade", False)
    entete = f"[ESCALADE - À TRAITER PAR UN HUMAIN] #{numero}" if escalade else f"Brouillon #{numero}"

    bloc = (
        f"{entete} - {entree['id']}\n"
        f"{'=' * 60}\n"
        f"Client        : {entree['client']}\n"
        f"Canal         : {entree['canal']}\n"
        f"Catégorie     : {entree['type_probleme']}\n"
        f"Statut        : {entree.get('statut', 'N/A')}\n"
        f"Expéditeur    : {entree.get('expediteur', 'N/A')}\n"
        f"Date          : {entree.get('date', 'N/A')}\n"
    )

    if escalade:
        signaux = ", ".join(entree.get("signaux_escalade", [])) or "N/A"
        bloc += f"Signaux       : {signaux}\n"

    bloc += (
        f"\n"
        f"--- Message original ---\n"
        f"{entree['message_original']}\n"
    )

    if escalade:
        bloc += (
            f"\n"
            f"--- Brouillon ---\n"
            f"Aucun brouillon généré : ce ticket nécessite une prise en charge humaine.\n"
        )
    else:
        bloc += (
            f"\n"
            f"--- Brouillon proposé ---\n"
            f"{entree['brouillon']}\n"
        )

    return bloc


def notifier():
    file_attente = charger_file_attente()

    if not file_attente:
        message = "Aucun ticket en attente."
        print(message)
        with open(FICHIER_A_APPROUVER, "w", encoding="utf-8") as f:
            f.write(message + "\n")
        return

    nb_escalades = sum(1 for e in file_attente if e.get("escalade"))
    entetes = (
        f"{len(file_attente)} ticket(s) en attente "
        f"({nb_escalades} escalade(s) à traiter par un humain, "
        f"{len(file_attente) - nb_escalades} brouillon(s) à valider)\n"
    )
    blocs = [formater_entree(entree, i + 1) for i, entree in enumerate(file_attente)]
    contenu = entetes + "\n" + ("\n" + "-" * 60 + "\n\n").join(blocs)

    print(contenu)

    with open(FICHIER_A_APPROUVER, "w", encoding="utf-8") as f:
        f.write(contenu)

    print(f"(Écrit également dans {FICHIER_A_APPROUVER.name})")


if __name__ == "__main__":
    notifier()
