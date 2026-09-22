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
    return (
        f"Brouillon #{numero} - {entree['id']}\n"
        f"{'=' * 60}\n"
        f"Client        : {entree['client']}\n"
        f"Canal         : {entree['canal']}\n"
        f"Catégorie     : {entree['type_probleme']}\n"
        f"Expéditeur    : {entree.get('expediteur', 'N/A')}\n"
        f"Date          : {entree.get('date', 'N/A')}\n"
        f"\n"
        f"--- Message original ---\n"
        f"{entree['message_original']}\n"
        f"\n"
        f"--- Brouillon proposé ---\n"
        f"{entree['brouillon']}\n"
    )


def notifier():
    file_attente = charger_file_attente()

    if not file_attente:
        message = "Aucun brouillon en attente de validation."
        print(message)
        with open(FICHIER_A_APPROUVER, "w", encoding="utf-8") as f:
            f.write(message + "\n")
        return

    entetes = f"{len(file_attente)} brouillon(s) en attente de validation\n"
    blocs = [formater_entree(entree, i + 1) for i, entree in enumerate(file_attente)]
    contenu = entetes + "\n" + ("\n" + "-" * 60 + "\n\n").join(blocs)

    print(contenu)

    with open(FICHIER_A_APPROUVER, "w", encoding="utf-8") as f:
        f.write(contenu)

    print(f"(Écrit également dans {FICHIER_A_APPROUVER.name})")


if __name__ == "__main__":
    notifier()
