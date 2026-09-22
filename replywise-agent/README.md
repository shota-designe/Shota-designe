# ReplyWise Agent (V0 / prototype)

Prototype d'agent IA de service client pour e-commerce. Il lit des messages
entrants, génère des brouillons de réponse adaptés au ton de chaque marque,
et les met en attente de validation humaine avant tout envoi.

**Statut : chantier V0, pas encore en production.** Rien n'est connecté à
une vraie boîte mail ou à une vraie API d'avis (Trustpilot, Google...) : le
code prépare juste la structure pour brancher ça plus tard.

## Fonctionnement général

1. `pipeline.py` lit `client_profiles.json` (le ton et les consignes de
   chaque marque cliente) et `incoming_messages.json` (les messages reçus).
2. Pour chaque message, il construit un prompt (`build_prompt`) adapté au
   **canal** du message, puis demande à l'IA un brouillon de réponse et une
   **catégorie de problème**.
3. Le résultat est écrit dans `pending_queue.json` : rien n'est jamais
   envoyé automatiquement, tout attend une relecture humaine.
4. `notifier.py` relit `pending_queue.json` et affiche clairement (terminal
   + fichier `a_approuver.txt`) la liste des brouillons à valider.

## Mode MOCK (par défaut)

Tant qu'aucune clé API n'est configurée, tout tourne en local sans appel
réseau :

```bash
cd replywise-agent
python3 pipeline.py
python3 notifier.py
```

En mode MOCK, la catégorisation est faite par une détection de mots-clés
(`deduire_categorie`) et les brouillons sont des réponses simulées, pour
pouvoir tester tout le pipeline sans dépendre d'Anthropic.

## Mode API réelle (plus tard)

Pour brancher une vraie IA :

```bash
pip install anthropic
export ANTHROPIC_API_KEY="sk-..."
python3 pipeline.py
```

Dans ce mode, l'IA reçoit le prompt et renvoie un JSON
`{"brouillon": "...", "type_probleme": "..."}` en une seule fois. Si la
catégorie renvoyée n'est pas valide ou si le JSON est mal formé, le script
retombe sur la détection par mots-clés (`deduire_categorie`) pour ne jamais
bloquer le pipeline.

## Les canaux (`canal`)

Chaque message dans `incoming_messages.json` a un champ `canal` :

- `"email"` : message privé. Le ton utilisé est celui du profil du client
  (`client_profiles.json` -> champ `ton`), personnalisé par marque.
- `"avis_public"` : avis laissé publiquement (ex : Trustpilot, Google
  Avis). Le ton devient "relations publiques" : diplomate, jamais
  défensif, pensé pour les futurs clients qui liront cette réponse. Le
  brouillon ne révèle jamais d'informations confidentielles (numéro de
  commande, montant de remboursement...) et invite à poursuivre l'échange
  en privé.

Aucune vraie API Trustpilot/Google n'est branchée : c'est un champ de
données qui prépare le terrain pour une intégration future.

## Catégorisation automatique (`type_probleme`)

Chaque brouillon dans `pending_queue.json` porte un champ `type_probleme`,
choisi parmi ces catégories exactes (alignées sur le suivi Notion, ne pas
renommer) :

- `Livraison/retard`
- `Remboursement/retour`
- `Produit défectueux`
- `Annulation abonnement`
- `Réclamation répétée (relance)`
- `Question générale`
- `Autre`

La catégorie est déduite du message (mots-clés en mode MOCK, ou demandée à
l'IA en même temps que le brouillon en mode réel).

## Notification des brouillons en attente

`notifier.py` ne connecte aucun vrai système d'email/Slack pour l'instant.
Il se contente de rendre visible ce qu'il y a à valider :

```bash
python3 notifier.py
```

- Affichage dans le terminal de chaque brouillon (client, canal, catégorie,
  message original, brouillon proposé).
- Écriture du même contenu dans `a_approuver.txt`, pour le relire
  facilement sans repasser par le terminal.

Pensé pour être remplacé plus tard par une vraie notification (email
interne, Slack...) sans changer le reste du pipeline.

## Fichiers

- `client_profiles.json` : profils des marques clientes (ton, secteur,
  consignes spécifiques, signature).
- `incoming_messages.json` : messages entrants (email ou avis public).
- `pipeline.py` : génère les brouillons + catégorisation -> `pending_queue.json`.
- `pending_queue.json` : file d'attente générée (brouillons à valider).
- `notifier.py` : affiche/écrit la liste des brouillons en attente
  (`a_approuver.txt`).
