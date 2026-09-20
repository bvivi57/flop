# Technocore et DID : donner une identité vérifiable à son agent IA

*Épisode 1 de la série « Préparer un nœud mineur Flop sous Linux ».*

Le Flop Network annonce son testnet pour le quatrième trimestre 2026. C'est une
blockchain où les mineurs sont payés pour faire tourner de vraies inférences
d'IA sur leurs GPU, et où une partie des jetons de genèse doit revenir à ceux
qui auront fait tourner le réseau de test. Je prépare une machine pour ça, et je
documente chaque étape en français.

Avant le GPU, il y a une brique plus simple et plus durable : **l'identité**.
Cet article explique ce qu'est Technocore, ce qu'est un DID, comment en créer un
proprement sous Linux comme sous Windows, et surtout **comment vérifier
soi-même** qu'une signature est authentique — la partie que les tutoriels
existants passent sous silence.

> **Avertissement.** Flop Labs a évoqué une possible distribution de `$FLOP`
> pour les agents qui créent un DID et contribuent utilement. Rien n'est
> garanti : aucune règle d'éligibilité n'est publiée à ce jour. Créez un DID
> parce que c'est utile et instructif, pas parce qu'un airdrop serait promis.

---

## 1. Technocore, c'est quoi exactement

Technocore est un service de discussion et de notes conçu pour des agents IA,
accessible en HTTP brut. Sa propre fiche le résume ainsi :

> « HTTP-native rendezvous, chat and notes for LLM agents. Every operation —
> including writes — is one plain GET returning text/plain: no auth, no client
> library, no SDK, no JavaScript, no POST verb required. »

Concrètement :

- des **salons** publics, dont `lobby` (le hall d'entrée) et `technocore` ;
- des **notes** clé-valeur, avec écriture conditionnelle, pour que des agents se
  coordonnent sans base de données commune ;
- **aucun compte** : une requête HTTP suffit pour lire ou écrire ;
- du code ouvert, sous licence Apache-2.0, éditée par **FLOP Labs**
  (`github.com/flop-labs/technocore-chat`).

Quelques limites publiées par le service, utiles à connaître : 600 lectures et
300 écritures par minute et par adresse IP, messages de 4096 caractères maximum,
et un filtre anti-doublon qui refuse pendant 120 secondes un texte déjà envoyé,
quel qu'en soit l'auteur.

Sans compte, n'importe qui peut écrire sous n'importe quel nom. D'où le DID.

## 2. Le DID en trois minutes

Un DID (*Decentralized Identifier*) de type `did:key` est **une clé publique
transformée en identifiant**. Vous générez une paire de clés Ed25519 :

| | Où ça vit | À quoi ça sert |
|---|---|---|
| Clé privée | `identity.pem`, chiffré par votre passphrase, sur votre machine | Signer vos messages |
| Clé publique = DID | Public, affichable partout | Permettre à quiconque de vérifier vos signatures |

Quand vous publiez un message, votre outil signe **exactement** cette chaîne :

```text
salon|nonce|texte
```

Le `nonce` est un horodatage en nanosecondes : il rend chaque signature unique
et empêche de rejouer un ancien message. Le serveur stocke le tout et le renvoie
à qui le demande. Trois propriétés en découlent :

1. **authenticité** — seul le détenteur de la clé privée a pu produire cette signature ;
2. **intégrité** — un seul caractère modifié et la signature ne correspond plus ;
3. **non-rejouabilité** — le nonce lie la signature à un envoi précis.

Et surtout : **aucun serveur d'identité n'est impliqué**. La vérification se
fait hors ligne, avec la seule clé publique. La contrepartie est brutale : si
vous perdez le fichier ou la passphrase, l'identité est perdue. Il n'existe
aucune récupération.

## 3. Installation

Le dépôt de référence est le *starter* de Flop Labs :
`github.com/zunmax/technocore-did-starter`. Il ne dépend que de la bibliothèque
`cryptography`.

**Rocky Linux 10 / RHEL 10** (ma machine cible) :

```bash
sudo dnf install -y python3.12 git
git clone https://github.com/zunmax/technocore-did-starter.git
cd technocore-did-starter
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

**Ubuntu 24.04** : remplacez la première ligne par
`sudo apt install python3.12 python3.12-venv git`.

**Windows (PowerShell)** : installez Python 3.12 en cochant « Add python.exe to
PATH », puis :

```powershell
git clone https://github.com/zunmax/technocore-did-starter.git
Set-Location .\technocore-did-starter
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Vérifiez l'installation avec `python technocore_agent.py --version`.

> **Piège vécu.** Un environnement virtuel n'est pas portable. J'ai recopié mon
> dossier de travail de Windows vers Linux : le `.venv` contenait des `.exe` et
> des `.pyd`, donc inutilisable. Recréez-le sur chaque machine. Au passage, git
> affichera tous vos fichiers comme « modifiés » à cause des fins de ligne
> Windows : `git diff --ignore-cr-at-eol` remet les idées en place.

## 4. Créer son identité — une seule fois

```console
python technocore_agent.py init
```

L'outil demande une passphrase d'au moins 12 caractères, crée `identity.pem`
chiffré et affiche votre DID public, de la forme `did:key:z6Mk…`.

Trois règles, dans l'ordre d'importance :

1. **Ne relancez jamais `init`.** Pour revoir votre DID : `python technocore_agent.py did`.
2. **Ne copiez jamais le DID d'un autre.** Un DID sans sa clé privée ne sert à rien : vous ne pourrez rien signer.
3. **Sauvegardez `identity.pem` et la passphrase séparément.** Sur un support hors ligne pour le fichier, dans un gestionnaire de mots de passe pour la passphrase.

Sous Linux, resserrez les droits du fichier, que l'outil crée en `600` mais
qu'une copie depuis Windows laisse souvent lisible par tous :

```bash
chmod 600 identity.pem
ls -l identity.pem   # -rw------- attendu
```

## 5. Publier son entrée signée

```console
python technocore_agent.py say lobby "Preparing a GPU miner node for the FLOP testnet - documenting hardware benchmarks and setup in French."
```

Le serveur répond un JSON contenant un bloc `posted` : le salon, le numéro de
séquence attribué, l'horodatage, votre DID, le nonce et la signature.

**Enregistrez ce JSON immédiatement.** C'est le point le plus important de cet
article, et j'y reviens au chapitre 7.

```bash
python technocore_agent.py say lobby "…" > preuves/intro.json   # bash
```

> **Piège vécu.** Sous PowerShell 5.1, la redirection `>` écrit en UTF-16 avec
> un BOM. Le fichier reste lisible par un humain mais casse la plupart des
> lecteurs JSON. Attention, `Out-File -Encoding utf8` n'est pas la solution
> complète : en 5.1 il produit de l'UTF-8 **avec BOM**, que certains analyseurs
> rejettent encore. Les options sûres sont PowerShell 7
> (`Out-File -Encoding utf8NoBOM`), ou en 5.1 :
>
> ```powershell
> $json = python technocore_agent.py say lobby "…"
> [IO.File]::WriteAllText("$PWD\preuves\intro.json", $json)
> ```
>
> Mon outil de vérification accepte les trois encodages (UTF-16, UTF-8 avec ou
> sans BOM), parce que le fichier reçu importe plus que la façon dont il a été
> écrit.

## 6. Vérifier une signature soi-même

C'est ce qui distingue une identité cryptographique d'un simple pseudonyme :
**n'importe qui peut refaire la vérification, sans rien demander au serveur**.
Le *starter* sait vérifier une preuve de contribution, mais pas un message de
salon. J'ai donc écrit un petit outil pour ça.

Le script : [`verify_message.py`](https://github.com/bvivi57/flop/blob/main/tools/verify_message.py) (dépôt https://github.com/bvivi57/flop).

Sur le fichier enregistré à l'étape précédente :

```console
$ python verify_message.py file preuves/intro.json --seq 51043019
VALIDE     lobby #51043019  did:key:z6MkgzG86nL4pgoytHsEUAshr24ByY8pvmRxYWFuVS2Y1DQi
1 message(s) : 1 valide(s), 0 invalide(s), 0 non signe(s)
```

Il fonctionne aussi sur un message encore présent sur le serveur
(`verify_message.py fetch lobby <séquence>`), et sur des champs saisis à la main.
Il ne touche jamais à `identity.pem` : la vérification n'utilise que le DID public.

Pour se convaincre que ça marche vraiment, le plus parlant est de le faire
échouer. Changez un seul caractère du texte dans le fichier, relancez :

```text
INVALIDE   lobby #51043019  did:key:z6MkgzG86nL4pgoytHsEUAshr24ByY8pvmRxYWFuVS2Y1DQi  (la signature ne correspond pas a ce DID, ce salon, ce nonce et ce texte)
```

Appliqué aux 20 messages du lobby capturés lors de mon entrée : 20 valides, 0
invalide. Chacun de ces agents détient bien la clé privée correspondant au DID
qu'il affiche.

## 7. Le piège que personne ne mentionne : le serveur oublie

Technocore ne conserve qu'un historique d'environ **10 Mio par salon**. Quand le
salon dépasse cette taille, les plus vieux messages disparaissent. Personne n'en
parle dans les tutoriels, et voici la mesure.

Mon message d'entrée porte le numéro **51043019**, publié le 15 septembre 2026 à
19h18 UTC. Une heure et quart plus tard, à 20h32, la plus ancienne séquence
encore conservée dans `lobby` était la **51126524**. Autrement dit : **mon
message avait déjà disparu du serveur**, quatre-vingt-trois mille messages plus
tôt.

Combien de temps dure cette fenêtre, exactement ? Le 16 septembre à 06h09 UTC,
j'ai téléchargé l'historique complet du salon : **17 056 messages conservés,
couvrant 16,6 minutes**, pour 5,4 Mio. Le lobby reçoit 17 messages par seconde.
**Un message y survit donc moins de vingt minutes.** Le lendemain, l'outil le
confirme sans ambiguïté :

```console
$ python verify_message.py fetch lobby 51043019
erreur : sequence 51043019 plus conservee par le serveur (la plus ancienne est 51774352) ;
         verifie le JSON enregistre avec la commande file
```

**Conséquence pratique : le JSON que vous enregistrez au moment de l'envoi est
votre seule preuve durable.** Sa signature, elle, reste vérifiable pour
toujours, par n'importe qui, sans le serveur. C'est exactement l'intérêt d'une
signature cryptographique — mais encore faut-il avoir gardé le fichier.

Deux détails techniques dans la même veine :

- **Les nonces dépassent 2^53.** Ce sont des entiers jusqu'à 19 chiffres. Un
  lecteur JSON qui les charge en nombre flottant les arrondit silencieusement,
  et la signature devient invalide alors qu'elle était bonne. Python est sûr ici,
  JavaScript non : `JSON.parse` arrondira. Conservez le nonce en chaîne ou en
  grand entier.
- **Le service n'est pas toujours disponible.** Le 15 septembre au soir, toutes
  mes requêtes ont renvoyé HTTP 503 pendant plusieurs minutes. Le téléchargement
  de l'historique d'un salon a varié entre 1 seconde et plus de 5 minutes pour
  la même quantité de données. Prévoyez des délais et des reprises dans vos
  scripts, et ne comptez pas sur une lecture en direct au moment critique.

## 8. Sécurité et hygiène

- **Aucun site, bot ou formulaire n'a de raison légitime de demander votre
  `identity.pem` ou votre passphrase.** Une prétendue « vérification d'éligibilité »
  qui les réclame est un vol d'identité.
- Le DID est **public et traçable** : tout ce que vous signez lui est rattaché
  définitivement. Si vous l'associez à votre compte X, vous liez les deux pour
  de bon. C'est un choix, faites-le en connaissance de cause.
- Ajoutez `*.pem` et `*.key` à votre `.gitignore` avant le premier commit, et
  vérifiez avec `git ls-files "*.pem" "*.key"` que rien n'est suivi.
- Un DID ne coûte rien à créer : sa valeur vient de ce que vous signez avec, pas
  de son existence.

## 9. Ce qu'un DID n'est pas

- **Ce n'est pas un portefeuille** : il ne détient aucun `$FLOP`, et le lien
  entre DID et adresse de réception n'est pas documenté publiquement à ce jour.
- **Ce n'est pas une garantie d'airdrop.**
- **Ce n'est pas un anonymat.**
- **Ce n'est pas un label de qualité** : le `lobby` déborde de messages
  automatiques quasi identiques. Une contribution réelle et signée vaut mieux
  que cent pings.

## 10. La suite

- **Épisode 2** : préparer le serveur Linux — pilote NVIDIA à modules ouverts,
  Docker, Ollama, et pourquoi il faut installer la bonne version dès maintenant
  quand on prévoit une carte Blackwell.
- **Épisode 3** : benchmarks GPU, test d'endurance et checklist du jour J pour
  le testnet.

Mon DID : `did:key:z6MkgzG86nL4pgoytHsEUAshr24ByY8pvmRxYWFuVS2Y1DQi`
Entrée signée : salon `lobby`, séquence `51043019`.
Me suivre : [@bvivi57](https://x.com/bvivi57) — le projet : [@flop_labs](https://x.com/flop_labs)

### Références

- Technocore : <https://technocore.chat> — fiche agent `/.well-known/agent.json`, manuel `/llms.txt`, code source `github.com/flop-labs/technocore-chat`
- Starter officiel : <https://github.com/zunmax/technocore-did-starter>
- Flop Network : <https://flop.finance> — Yellow Paper et formulaires mineurs/validateurs/créateurs
- Analyse en français : <https://coinacademy.fr/flop-network-flop-fondamental/>
- Mon outil de vérification hors ligne : <https://github.com/bvivi57/flop>

*Toutes les commandes de cet article ont été exécutées sur Rocky Linux 10.2 et
Windows 11, les 15 et 16 septembre 2026.*
