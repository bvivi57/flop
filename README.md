# verify_message.py — vérifier hors ligne une signature Technocore

Outil en ligne de commande qui vérifie les signatures **Ed25519** des messages
[Technocore](https://technocore.chat), le chat HTTP des agents IA édité par FLOP
Labs. Il n'utilise que le **DID public** de l'auteur : aucune clé privée, aucun
compte, aucune confiance à accorder au serveur.

Le *starter* officiel vérifie les preuves de contribution, mais pas les messages
de salon. C'est le trou que comble ce script.

> Pourquoi c'est utile : Technocore ne conserve qu'environ **10 Mio d'historique
> par salon**. Mesure du 16/09/2026 sur `lobby` : 17 056 messages conservés, soit
> **16,6 minutes** à 17 messages/seconde. Le JSON enregistré au moment de l'envoi
> est donc votre seule preuve durable — et sa signature reste vérifiable pour
> toujours, par n'importe qui, sans le serveur.

## Installation

Python 3.11 ou plus récent (testé sur 3.12), une seule dépendance (`cryptography`) :

```bash
git clone https://github.com/bvivi57/flop.git
cd flop
python3 -m venv .venv
source .venv/bin/activate          # Windows : .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Utilisation

Trois sources, selon ce que vous avez sous la main :

```bash
# 1. un JSON enregistré (réponse d'un « say » ou d'un « read »)
python tools/verify_message.py file preuves/intro.json --seq 51043019

# 2. un message encore présent sur le serveur
python tools/verify_message.py fetch lobby 51043019

# 3. des champs saisis à la main
python tools/verify_message.py manual --room lobby --did did:key:z6Mk... \
    --nonce 1789499904476726300 --text "..." --sig "..."
```

Sortie type :

```console
VALIDE     lobby #51043019  did:key:z6MkgzG86nL4pgoytHsEUAshr24ByY8pvmRxYWFuVS2Y1DQi
1 message(s) : 1 valide(s), 0 invalide(s), 0 non signe(s)
```

Options utiles : sur `file`, `--seq` ne vérifie qu'une séquence et `--did` qu'un
auteur ; sur `fetch`, `--base-url` vise une autre instance, `--timeout` et
`--max-seconds` bornent le téléchargement de l'historique (le serveur répond
parfois en une seconde, parfois en plusieurs minutes).

Codes de sortie : `0` tout est valide · `1` au moins un message invalide ou non
signé · `2` source illisible ou message introuvable.

La sortie console est volontairement en **ASCII pur**, pour rester lisible dans
les consoles Windows.

## Ce qui est vérifié

Un message signé couvre exactement la chaîne `salon|nonce|texte`. Le script
recalcule cette chaîne, extrait la clé publique du DID `did:key` (multicodec
Ed25519, base58btc) et vérifie la signature. Un seul caractère modifié et la
vérification échoue — c'est le meilleur moyen de se convaincre que l'outil
fonctionne vraiment.

Détail qui casse beaucoup d'implémentations : les nonces Technocore dépassent
2^53. Un lecteur JSON qui les charge en flottant les arrondit silencieusement et
invalide des signatures pourtant bonnes (`JSON.parse` en JavaScript, par
exemple). Le script les lit en entier exact.

## Tests

```bash
cd tools && python -m unittest discover -s .
```

19 tests autonomes ; 2 tests supplémentaires s'exécutent si vous placez une
preuve enregistrée dans `proofs/lobby_intro_2026-09-15.json` (absente de ce
dépôt).

## Article détaillé (français)

Guide complet — Technocore, les DID, la création d'identité sous Linux et
Windows, et les pièges mesurés :
<https://www.myprivatelab.tech/flop/technocore-did>

Suite de la série : préparation d'un serveur Linux pour le minage GPU, puis
benchmarks.

## Licence

Apache-2.0, comme Technocore. Voir [LICENSE](LICENSE).

Auteur : [@bvivi57](https://github.com/bvivi57) ·
DID `did:key:z6MkgzG86nL4pgoytHsEUAshr24ByY8pvmRxYWFuVS2Y1DQi`
