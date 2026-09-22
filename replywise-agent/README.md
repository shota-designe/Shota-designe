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
2. Pour chaque message, il vérifie d'abord s'il faut une **escalade
   humaine** (`detecter_escalade`). Si oui, aucun appel à l'IA n'est fait :
   le ticket est directement marqué pour un humain.
3. Sinon, il construit un prompt (`build_prompt`) adapté au **canal** du
   message, puis demande à l'IA un brouillon de réponse et une
   **catégorie de problème**.
4. Le résultat est écrit dans `pending_queue.json` : rien n'est jamais
   envoyé automatiquement, tout attend une relecture humaine (`statut`
   à `en_attente_approbation` ou `a_traiter_par_humain`).
5. `notifier.py` relit `pending_queue.json` et affiche clairement (terminal
   + fichier `a_approuver.txt`) la liste des tickets en attente, brouillons
   comme escalades.

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

## Détection d'escalade (`detecter_escalade`)

Certains messages ne doivent pas recevoir de brouillon généré par l'IA :
ils doivent être traités directement par un humain. `detecter_escalade`
(dans `pipeline.py`) analyse le texte du message et repère 5 signaux,
uniquement par mots-clés (pas de vrai NLP, volontairement simple pour ce
prototype) :

1. **Menace juridique / litige** : `avocat`, `tribunal`, `plainte`,
   `poursuite`, `litige`, "action en justice", "mise en demeure"...
2. **Montant élevé** : un montant en euros détecté dans le message
   au-dessus de `SEUIL_MONTANT_ELEVE` (300 € par défaut, à ajuster selon
   le client).
3. **Contact répété non résolu** : le client indique explicitement que
   c'est sa 3e fois (ou plus) — "3e fois", "3ème fois", "encore une
   fois", "toujours pas de réponse depuis"...
4. **Fraude suspectée** : `chargeback`, "contestation de paiement",
   `escroquerie`, `arnaque`, "vous m'avez volé"...
5. **Colère extrême / menace d'exposition publique** : "tout le monde",
   "réseaux sociaux", `scandaleux`, `inadmissible`, "dénoncer"...

Dès qu'**un seul** signal est détecté :

- le ticket dans `pending_queue.json` a `"escalade": true` et
  `"signaux_escalade"` liste le(s) signal(aux) détecté(s) (en toutes
  lettres, ex. `"Menace juridique / litige"`) ;
- `"statut"` passe à `"a_traiter_par_humain"` (au lieu de
  `"en_attente_approbation"`) ;
- `"brouillon"` reste à `null` : **aucun appel à l'IA n'est fait**, on ne
  génère qu'un signalement clair pour la personne qui reprend la main.

Si aucun signal n'est détecté, le pipeline continue normalement (le
brouillon est généré comme avant). La catégorisation (`type_probleme`)
reste calculée même pour un ticket escaladé, pour donner du contexte à
l'humain qui le reprend.

Ce n'est qu'une première passe par mots-clés : les seuils et listes de
mots-clés sont volontairement simples et à affiner avec de vrais cas
clients.

## Notification des brouillons en attente

`notifier.py` ne connecte aucun vrai système d'email/Slack pour l'instant.
Il se contente de rendre visible ce qu'il y a à valider :

```bash
python3 notifier.py
```

- Affichage dans le terminal de chaque ticket (client, canal, catégorie,
  statut, message original, et brouillon proposé — ou signaux d'escalade
  et mention "aucun brouillon" si le ticket doit être traité par un humain).
- Écriture du même contenu dans `a_approuver.txt`, pour le relire
  facilement sans repasser par le terminal.

Pensé pour être remplacé plus tard par une vraie notification (email
interne, Slack...) sans changer le reste du pipeline.

## Fichiers

- `client_profiles.json` : profils des marques clientes (ton, secteur,
  consignes spécifiques, signature).
- `incoming_messages.json` : messages entrants (email ou avis public),
  dont 3 exemples déclenchant chacun un signal d'escalade différent
  (`msg_007` juridique, `msg_008` montant élevé, `msg_009` fraude).
- `pipeline.py` : détecte l'escalade, génère les brouillons + la
  catégorisation -> `pending_queue.json`.
- `pending_queue.json` : file d'attente générée (brouillons à valider et
  tickets escaladés).
- `notifier.py` : affiche/écrit la liste des tickets en attente
  (`a_approuver.txt`).
