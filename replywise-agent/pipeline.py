"""
ReplyWise - Pipeline principal (V0 / prototype)

Ce script lit les messages entrants (emails privés ou avis publics),
génère un brouillon de réponse adapté au ton du client et au canal,
déduit une catégorie de problème, puis dépose le tout dans une file
d'attente (pending_queue.json) en attendant une validation humaine.

Mode MOCK : si la variable d'environnement ANTHROPIC_API_KEY n'est pas
définie, le script fonctionne entièrement en local avec des réponses
simulées (aucun appel réseau, aucune clé requise). C'est le mode par
défaut tant qu'on n'a pas encore de vrai client sous contrat.
"""

import json
import os
import re
from pathlib import Path

DOSSIER = Path(__file__).parent
FICHIER_PROFILS = DOSSIER / "client_profiles.json"
FICHIER_MESSAGES = DOSSIER / "incoming_messages.json"
FICHIER_QUEUE = DOSSIER / "pending_queue.json"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MOCK_MODE = not ANTHROPIC_API_KEY

# Catégories exactes utilisées dans le suivi Notion : ne pas renommer.
CATEGORIES = [
    "Livraison/retard",
    "Remboursement/retour",
    "Produit défectueux",
    "Annulation abonnement",
    "Réclamation répétée (relance)",
    "Question générale",
    "Autre",
]

# Indices textuels utilisés pour reconnaître une relance / réclamation répétée.
INDICES_RELANCE = [
    "deuxième fois",
    "2ème fois",
    "toujours pas de réponse",
    "toujours pas eu de réponse",
    "je reviens vers vous",
    "sans réponse",
    "encore une fois",
]

# Libellés des signaux d'escalade (repris tels quels dans pending_queue.json).
SIGNAL_JURIDIQUE = "Menace juridique / litige"
SIGNAL_MONTANT = "Montant élevé"
SIGNAL_CONTACT_REPETE = "Contact répété non résolu"
SIGNAL_FRAUDE = "Fraude suspectée"
SIGNAL_COLERE = "Colère extrême / menace d'exposition publique"

SEUIL_MONTANT_ELEVE = 300  # en euros, seuil arbitraire pour le prototype


def charger_json(chemin):
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def charger_profils():
    return charger_json(FICHIER_PROFILS)


def charger_messages():
    return charger_json(FICHIER_MESSAGES)


def deduire_categorie(message):
    """Catégorisation par mots-clés, utilisée en mode MOCK et comme
    filet de sécurité si l'IA ne renvoie pas de catégorie exploitable."""
    texte = message["message"].lower()

    est_relance = message.get("historique_client") == "reclamation_precedente_sans_reponse"
    est_relance = est_relance or any(indice in texte for indice in INDICES_RELANCE)
    if est_relance:
        return "Réclamation répétée (relance)"

    if "abonnement" in texte:
        return "Annulation abonnement"

    if re.search(r"défectueu|cassé|fissuré|ne fonctionne pas|ne s'allume pas|abîmé|abimé", texte):
        return "Produit défectueux"

    if "rembours" in texte or "retour" in texte:
        return "Remboursement/retour"

    if re.search(r"livraison|retard|colis|statut de ma commande|numéro de suivi", texte):
        return "Livraison/retard"

    if "?" in texte and re.search(r"tarif|propos|information|combien|possible de", texte):
        return "Question générale"

    return "Autre"


def _contient_montant_eleve(texte):
    """Cherche un montant en euros dans le texte et renvoie True s'il
    dépasse SEUIL_MONTANT_ELEVE (détection simple, pas de NLP)."""
    montants = re.findall(r"(\d{1,3}(?:[ .]?\d{3})*)\s?(?:€|euros?)", texte)
    for montant in montants:
        valeur = int(montant.replace(" ", "").replace(".", ""))
        if valeur >= SEUIL_MONTANT_ELEVE:
            return True
    return False


def detecter_escalade(message_text):
    """Repère les signaux qui indiquent qu'un ticket doit être traité par
    un humain plutôt que par l'IA seule. Renvoie la liste des libellés de
    signaux détectés (liste vide si aucun signal ne se déclenche)."""
    texte = message_text.lower()
    signaux = []

    if re.search(r"avocat|tribunal|plainte|poursuite|litige|action en justice|mise en demeure", texte):
        signaux.append(SIGNAL_JURIDIQUE)

    if _contient_montant_eleve(texte):
        signaux.append(SIGNAL_MONTANT)

    if re.search(
        r"3e fois|3ème fois|troisième fois|4e fois|4ème fois|quatrième fois|"
        r"encore une fois|toujours pas de réponse depuis",
        texte,
    ):
        signaux.append(SIGNAL_CONTACT_REPETE)

    if re.search(
        r"chargeback|contestation de paiement|contest\w* le paiement|"
        r"escroquerie|arnaque|vous m'avez volé|c'est du vol",
        texte,
    ):
        signaux.append(SIGNAL_FRAUDE)

    if re.search(
        r"tout le monde|réseaux sociaux|dénonc\w*|balancer partout|"
        r"honte à vous|scandaleux|inadmissible",
        texte,
    ):
        signaux.append(SIGNAL_COLERE)

    return signaux


def build_prompt(message, profil_client, canal):
    """Construit le prompt envoyé à l'IA. Le ton change selon le canal :
    - email : ton du profil client (relation privée, one-to-one)
    - avis_public : ton "relations publiques", pensé pour les futurs
      clients qui liront la réponse publiquement (jamais défensif).
    """
    categories_str = "\n".join(f"- {c}" for c in CATEGORIES)

    if canal == "avis_public":
        consignes_ton = (
            "Ce message est un AVIS PUBLIC (ex: Trustpilot, Google Avis). "
            "Ta réponse sera visible par tous les futurs clients qui liront cet avis.\n"
            "Adopte donc un ton de relations publiques : diplomate, jamais défensif, "
            "jamais accusateur envers le client, même s'il a tort. Reconnais le "
            "désagrément, reste professionnel et rassurant sur le sérieux de "
            "l'entreprise, et propose de poursuivre l'échange en privé (email) "
            "pour résoudre le problème concret. Ne donne aucune information "
            "confidentielle (numéro de commande, remboursement précis, etc.) "
            "dans une réponse publique."
        )
    else:
        consignes_ton = (
            "Ce message est un EMAIL PRIVÉ. Réponds directement au client avec le "
            f"ton propre à cette marque : {profil_client['ton']}. "
            f"Consigne spécifique de la marque : {profil_client['consignes_specifiques']}"
        )

    prompt = f"""Tu es l'assistant de réponse client de {profil_client['nom_entreprise']}
({profil_client['secteur']}).

{consignes_ton}

Message reçu du client :
\"\"\"{message['message']}\"\"\"

Fais deux choses :
1. Rédige un brouillon de réponse signé "{profil_client['signature']}".
2. Classe ce message dans une seule des catégories suivantes (recopie le nom exactement) :
{categories_str}

Réponds uniquement avec un JSON de la forme :
{{"brouillon": "...", "type_probleme": "..."}}
"""
    return prompt


def generer_reponse_mock(message, profil_client, canal, categorie):
    """Simule la réponse de l'IA, sans aucun appel réseau."""
    if canal == "avis_public":
        brouillon = (
            f"Bonjour, merci d'avoir pris le temps de partager votre retour. "
            f"Nous sommes sincèrement désolés pour la gêne occasionnée et nous "
            f"prenons votre remarque très au sérieux. Afin de résoudre ce point "
            f"rapidement et personnellement, pourriez-vous nous écrire directement "
            f"par email ? Notre équipe s'engage à trouver une solution adaptée.\n\n"
            f"{profil_client['signature']}"
        )
    else:
        brouillon = (
            f"Bonjour,\n\n"
            f"Merci de nous avoir contactés. Nous avons bien pris connaissance de "
            f"votre message concernant : « {message['message'][:80]}{'...' if len(message['message']) > 80 else ''} ».\n\n"
            f"[Réponse simulée - mode MOCK, aucune clé API Anthropic configurée. "
            f"Catégorie détectée : {categorie}.]\n\n"
            f"Cordialement,\n{profil_client['signature']}"
        )
    return {"brouillon": brouillon, "type_probleme": categorie}


def appeler_ia(prompt, message, profil_client, canal):
    """Appelle l'IA (ou simule l'appel en mode MOCK) et renvoie
    un dict {"brouillon": ..., "type_probleme": ...}."""
    categorie_mock = deduire_categorie(message)

    if MOCK_MODE:
        return generer_reponse_mock(message, profil_client, canal, categorie_mock)

    # Mode réel : nécessite `pip install anthropic` et ANTHROPIC_API_KEY.
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    reponse = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    texte_brut = reponse.content[0].text.strip()

    try:
        # On retire d'éventuels ```json ... ``` autour de la réponse.
        texte_json = re.sub(r"^```(json)?|```$", "", texte_brut.strip(), flags=re.MULTILINE).strip()
        resultat = json.loads(texte_json)
        if resultat.get("type_probleme") not in CATEGORIES:
            resultat["type_probleme"] = categorie_mock
        return resultat
    except (json.JSONDecodeError, KeyError):
        # Filet de sécurité si l'IA ne renvoie pas un JSON exploitable.
        return {"brouillon": texte_brut, "type_probleme": categorie_mock}


def traiter_message(message, profils):
    profil_client = profils[message["client_id"]]
    canal = message.get("canal", "email")

    entree = {
        "id": message["id"],
        "client": profil_client["nom_entreprise"],
        "canal": canal,
        "date": message.get("date", ""),
        "expediteur": message.get("expediteur", ""),
        "message_original": message["message"],
    }

    signaux = detecter_escalade(message["message"])
    entree["escalade"] = bool(signaux)
    entree["signaux_escalade"] = signaux

    if signaux:
        # Escalade : on ne génère aucun brouillon IA, on se contente d'un
        # signalement clair pour qu'un humain reprenne la main.
        entree["type_probleme"] = deduire_categorie(message)
        entree["statut"] = "a_traiter_par_humain"
        entree["brouillon"] = None
        return entree

    prompt = build_prompt(message, profil_client, canal)
    resultat_ia = appeler_ia(prompt, message, profil_client, canal)

    entree["type_probleme"] = resultat_ia["type_probleme"]
    entree["statut"] = "en_attente_approbation"
    entree["brouillon"] = resultat_ia["brouillon"]
    return entree


def main():
    print(f"ReplyWise - Pipeline ({'MOCK' if MOCK_MODE else 'API réelle'})")
    print("-" * 60)

    profils = charger_profils()
    messages = charger_messages()

    file_attente = []
    nb_escalades = 0
    for message in messages:
        entree = traiter_message(message, profils)
        file_attente.append(entree)
        if entree["escalade"]:
            nb_escalades += 1
            statut_affiche = "ESCALADE -> humain (" + ", ".join(entree["signaux_escalade"]) + ")"
        else:
            statut_affiche = "brouillon généré"
        print(f"[{entree['canal']:^12}] {entree['client']} -> {entree['type_probleme']} [{statut_affiche}]")

    with open(FICHIER_QUEUE, "w", encoding="utf-8") as f:
        json.dump(file_attente, f, ensure_ascii=False, indent=2)

    print("-" * 60)
    print(f"{len(file_attente)} ticket(s) écrit(s) dans {FICHIER_QUEUE.name} "
          f"({nb_escalades} escalade(s), {len(file_attente) - nb_escalades} brouillon(s))")


if __name__ == "__main__":
    main()
