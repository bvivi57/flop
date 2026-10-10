# Pilote NVIDIA, Secure Boot, Docker et Ollama : préparer un serveur GPU sous Rocky Linux 10

*Épisode 2 de la série « Préparer un nœud mineur Flop sous Linux ».*

Dans l'épisode 1, j'ai donné une identité vérifiable à mon agent. Place au
matériel : une RTX 5070 Ti (16 Go, architecture Blackwell) passée d'un PC
Windows à un serveur Rocky Linux 10.2 dédié, qui tournera 24 h sur 24 pendant
le testnet du Flop Network.

Cet article couvre toute la pile, du pilote jusqu'au premier modèle qui répond :
modules noyau ouverts, Secure Boot, verrouillage de version, Docker avec accès
GPU, Ollama en service. Chaque commande a été exécutée sur la machine, et je
signale à chaque étape le piège sur lequel je suis tombé.

> **Avertissement.** Le Flop Network n'a publié ni code de nœud ni date
> officielle de testnet à ce jour. Ce serveur est utile en soi pour de
> l'inférence locale ; rien ne garantit une récompense future.

---

## 1. Pourquoi Linux, et pourquoi c'est important de figer le pilote

Trois raisons de quitter Windows pour un nœud :

- **la VRAM** : plus de bureau ni de couche graphique Windows qui en consomme ;
- **la stabilité** : pas de redémarrage imposé par une mise à jour ;
- **l'exploitation** : SSH, systemd, supervision, comme n'importe quel serveur.

Une quatrième raison est propre au Flop Network. Son Yellow Paper (v0.5.0)
prévoit une **recalibration complète du mineur en cas de changement de pilote ou
de carte**, la capacité déclarée étant un bail renouvelé tous les sept jours.
Une mise à jour automatique du pilote en plein testnet coûterait donc une
recalibration. D'où la règle que je me suis fixée : **installer la carte
définitive et son pilote définitif avant la première calibration, puis ne plus y
toucher.** Le chapitre 5 montre comment le garantir.

## 2. Le matériel, et un premier piège avant même le système

| Élément | Choix |
|---|---|
| CPU | Ryzen 9 7900X (12 cœurs), iGPU pour l'écran de dépannage |
| Carte mère | Gigabyte B650M (slot principal en PCIe 4.0 x16) |
| GPU | RTX 5070 Ti 16 Go, 300 W, câble 12V-2x6 natif de l'alimentation |
| Système | Rocky Linux 10.2, Secure Boot actif, SELinux en mode Enforcing |

Branchez l'écran sur la sortie de la carte mère : la carte graphique reste
dédiée au calcul.

**Vérifiez la largeur du lien PCIe avant tout le reste.** Sans pilote, `lspci`
suffit (paquet `pciutils`) :

```bash
sudo lspci -vv -s 01:00.0 | grep -E 'LnkCap|LnkSta'
```

> **Piège vécu.** Le matin du montage, ma carte était vue en **x8** au lieu de
> x16. Le soir, après un passage dans le BIOS, le lien était remonté à **x16** :
> le plus probable est que la carte était mal enfoncée la première fois. Une carte mal enfoncée ne provoque aucune erreur : elle
> marche, simplement avec deux fois moins de lignes.

Ne vous inquiétez pas non plus de voir **Gen1** une fois le pilote installé :
au repos, la carte réduit la vitesse du lien pour économiser de l'énergie, et
remonte en Gen4 sous charge. C'est la **largeur** (x16) qui doit rester stable.
Et une carte PCIe 5.0 dans un slot 4.0, c'est normal : l'impact sur l'inférence
est négligeable, puisque le modèle vit dans la VRAM.

## 3. Préparer le système

```bash
sudo dnf -y upgrade --refresh
sudo dnf -y install epel-release                  # fournit dkms
sudo dnf -y install dnf-plugins-core kernel-devel-$(uname -r) gcc make openssl mokutil
sudo reboot
```

Redémarrez après la mise à niveau : le paquet `kernel-devel` doit correspondre
**exactement** au noyau en cours d'exécution, sinon DKMS ne pourra pas compiler
le module. Après le redémarrage, vérifiez :

```bash
uname -r
rpm -q kernel-devel-$(uname -r)
```

## 4. Le pilote : modules ouverts obligatoires, Secure Boot à apprivoiser

### 4.1 Blackwell n'accepte que les modules ouverts

Les cartes RTX 50 **ne fonctionnent qu'avec les modules noyau ouverts** de
NVIDIA. Le paquet s'appelle `nvidia-open` ; les anciens modules propriétaires ne
les prennent pas en charge. Ces modules ouverts fonctionnent aussi sur les
générations précédentes (Turing et plus récentes) : si vous préparez le serveur
avec une ancienne carte en attendant la nouvelle, installez directement le bon
pilote.

```bash
sudo dnf config-manager --add-repo https://developer.download.nvidia.com/compute/cuda/repos/rhel10/x86_64/cuda-rhel10.repo
sudo dnf clean expire-cache
sudo dnf -y install dkms
sudo dnf -y install nvidia-open
```

> **Attention aux tutoriels pour EL8 et EL9.** La commande
> `dnf module enable nvidia-driver:open-dkms` qu'on y trouve ne s'applique pas à
> Rocky 10 : la modularité est dépréciée, les paquets s'installent directement.

Au moment de mes tests (septembre-octobre 2026), le dépôt `rhel10` fournissait
la branche **615.71.09**.

### 4.2 Secure Boot : la clé à enrôler

Avec Secure Boot actif, le noyau refuse de charger un module qui n'est pas signé
par une clé de confiance. Et le message d'erreur ne vous mettra pas sur la piste :
`nvidia-smi` répond seulement qu'il « n'arrive pas à communiquer avec le pilote ».

DKMS crée sa propre paire de clés dans `/var/lib/dkms` et signe chaque module
qu'il compile. Il reste à faire accepter cette clé par le micrologiciel :

```bash
sudo mokutil --import /var/lib/dkms/mok.pub     # choisir un mot de passe à usage unique
sudo reboot
```

Au redémarrage, un écran bleu **MOK Manager** apparaît avant le système :
`Enroll MOK` → `Continue` → `Yes`, puis le mot de passe choisi juste avant.

> **Bon à savoir.** Cet écran n'attend pas : il affiche un compte à rebours et
> démarre normalement si vous ne touchez à rien. Soyez devant la machine, avec un
> clavier branché. Sur un serveur sans écran, c'est le moment où il en faut un.

Il faut donc **deux redémarrages** au total : un après la mise à niveau du
système, un pour l'enrôlement.

### 4.3 Vérifier que tout est en place

```console
$ mokutil --sb-state
SecureBoot enabled
$ mokutil --list-enrolled | grep 'CN=DKMS'
        Issuer: CN=DKMS module signing key
        Subject: CN=DKMS module signing key
$ modinfo -F signer nvidia
DKMS module signing key
$ modinfo -F license nvidia
Dual MIT/GPL
$ grep 'Open Kernel' /proc/driver/nvidia/version
NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  615.71.09  Release Build ...
```

La licence `Dual MIT/GPL` et la mention `Open Kernel Module` confirment qu'il
s'agit bien des modules ouverts. Puis :

```console
$ nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
NVIDIA GeForce RTX 5070 Ti, 615.71.09, 16303 MiB
```

Deux vérifications de plus :

- **`nouveau`**, le pilote libre, ne doit pas être chargé (`lsmod | grep nouveau`
  ne renvoie rien). Le paquet NVIDIA s'en charge en ajoutant
  `rd.driver.blacklist=nouveau` à la ligne de démarrage du noyau : je n'ai rien
  eu à faire à la main.
- **`nvidia-persistenced`** garde le pilote initialisé entre deux tâches, ce qui
  évite un délai à chaque démarrage de calcul. Il était déjà actif chez moi ; à
  défaut : `sudo systemctl enable --now nvidia-persistenced`.

## 5. Figer la version : verrouiller tout le pilote, pas seulement le paquet principal

Le greffon `versionlock` de dnf empêche qu'un paquet change de version.

Le réflexe serait de verrouiller `nvidia-open`. C'est insuffisant : ce paquet ne
fait que regrouper une douzaine d'autres paquets, dont les bibliothèques CUDA.
Chez moi, l'installation en a posé **treize**, tous en 615.71.09. Verrouillez-les
tous :

```bash
sudo dnf -y install python3-dnf-plugin-versionlock
sudo dnf versionlock add $(rpm -qa --qf '%{NAME}\n' | grep -E '^(nvidia-|kmod-nvidia|libnvidia)' | grep -vE 'selinux|container')
dnf versionlock list
```

Les deux exclusions ont une raison :

- `nvidia-driver-selinux` suit sa propre numérotation (0.1), sans lien avec le pilote ;
- le **Container Toolkit** (chapitre 6), dont les paquets commencent aussi par
  `nvidia-` ou `libnvidia-`, évolue indépendamment du pilote. Sans ce filtre, si
  vous relancez la commande après l'avoir installé, vous le figez aussi par
  accident.

Le jour où vous changerez volontairement de pilote, ce qui impliquera une
recalibration : `sudo dnf versionlock clear`, mise à jour, puis reverrouillage
avec la même commande.

## 6. Docker et l'accès au GPU

```bash
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

dnf vous demandera d'accepter la clé de signature du dépôt Docker. Vérifiez son
empreinte avant de dire oui : `060A 61C5 1B55 8A7F 742B 77AA C52F EB6B 621E 9F35`.

Ensuite, le NVIDIA Container Toolkit, qui permet aux conteneurs d'accéder au GPU :

```bash
curl -sSL https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo | \
  sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo
sudo dnf -y install nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo docker run --rm --gpus all nvidia/cuda:13.0.0-base-ubuntu24.04 nvidia-smi
```

Trois remarques :

- **Ne vous ajoutez pas au groupe `docker`.** Beaucoup de tutoriels le
  conseillent pour se passer de `sudo`, mais appartenir à ce groupe revient à
  être root sur la machine. Sur un nœud exposé à Internet, `sudo docker` est le
  bon compromis.
- **SELinux peut rester en mode Enforcing.** On lit souvent qu'il faut le
  désactiver pour les GPU en conteneur : chez moi, le test a fonctionné du
  premier coup sans rien toucher. Si un conteneur précis se voit refuser l'accès
  au GPU, ajoutez `--security-opt label=disable` **à ce conteneur seulement**.
- **L'image de test** : je pensais utiliser une image CUDA 13.4 pour coller au
  pilote, mais ce tag n'existait pas encore sur Docker Hub. Pas de souci : une
  image CUDA 13.0 fonctionne avec un pilote plus récent, l'inverse n'étant pas
  vrai.

Versions installées le 10 octobre 2026 : Docker 29.9.0, Container Toolkit 1.20.1.

## 7. Ollama : lire le script avant de l'exécuter

La méthode officielle tient en une ligne : `curl -fsSL https://ollama.com/install.sh | sh`.
Elle exécute en root un script que vous n'avez pas lu, qui télécharge un binaire
sans vérifier de signature ni d'empreinte. J'ai préféré le télécharger, le lire,
puis exécuter la copie lue.

```bash
curl -fsSL https://ollama.com/install.sh -o install.sh
less install.sh
```

Ce que fait le script sur Rocky Linux 10, en résumé :

1. il installe le binaire dans `/usr/local/lib/ollama`, avec un lien dans `/usr/local/bin` ;
2. il crée un utilisateur système `ollama` (les modèles iront dans
   `/usr/share/ollama/.ollama/models`), l'ajoute aux groupes `video` et
   `render`, et **vous ajoute au groupe `ollama`** ;
3. il crée et démarre le service `ollama.service`, qui écoute sur `127.0.0.1:11434` ;
4. il contient aussi une partie qui **installe un pilote CUDA** si aucun n'est
   détecté. Sur une machine déjà équipée, elle ne s'exécute pas : le script
   s'arrête avant dès qu'il trouve `nvidia-smi`. Votre pilote verrouillé n'est
   pas touché.

Deux choses à régler **avant** de l'exécuter.

**Le prérequis `zstd`.** L'archive est compressée en `.tar.zst`, et le script
échoue sans l'outil de décompression :

```bash
sudo dnf -y install zstd
```

**La configuration du service.** Par défaut, Ollama traite **une seule requête
à la fois**. Sous Windows, j'avais mesuré qu'avec deux requêtes simultanées, le
débit total était même légèrement inférieur à celui d'une requête seule : elles
attendaient leur tour. Pour un serveur, il faut du parallélisme. Créez la
surcharge systemd avant l'installation, pour que le service démarre directement
avec les bons réglages :

```ini
# /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="PATH=/usr/local/bin:/usr/bin"
Environment="OLLAMA_NUM_PARALLEL=4"
Environment="OLLAMA_KEEP_ALIVE=24h"
Environment="OLLAMA_FLASH_ATTENTION=1"
```

> **Piège vécu.** La ligne `PATH` n'est pas là par hasard. Le script recopie
> dans le service **le PATH de la session qui l'exécute**, y compris
> `~/.local/bin` et `~/bin`. Le service pouvait donc lancer des programmes
> déposés dans mon dossier personnel. Rien de grave en pratique, mais il n'y a
> aucune raison de le laisser faire. Cette surcharge le restreint aux dossiers
> système.

Puis l'installation, en fixant la version :

```bash
sudo -v && OLLAMA_VERSION=0.40.2 sh install.sh
```

Le script affichera peut-être qu'il ne détecte pas de GPU, faute de `lspci`.
C'est sans conséquence : Ollama détecte la carte lui-même au démarrage.

### Vérifier que les réglages sont pris en compte

Ne vous contentez pas de savoir que le fichier existe : vérifiez ce que le
service a réellement lu.

```console
$ systemctl show ollama -p DropInPaths
DropInPaths=/etc/systemd/system/ollama.service.d/override.conf
$ journalctl -u ollama -b | grep -o 'OLLAMA_NUM_PARALLEL:[0-9]*'
OLLAMA_NUM_PARALLEL:4
$ journalctl -u ollama -b | grep 'inference compute'
... library=CUDA compute=12.0 description="NVIDIA GeForce RTX 5070 Ti" ... total="15.6 GiB" available="15.3 GiB"
$ ss -ltn | grep 11434
LISTEN 0  4096  127.0.0.1:11434  0.0.0.0:*
```

C'est grâce à ces vérifications que j'ai vu que mon premier essai n'avait rien
appliqué : la surcharge n'avait pas été écrite, et le journal affichait
`OLLAMA_NUM_PARALLEL:1`. Le service tournait parfaitement, simplement avec les
réglages par défaut.

La dernière ligne compte aussi : Ollama doit écouter **uniquement sur
`127.0.0.1`**. Son API n'a aucune authentification ; ne l'exposez jamais
directement sur le réseau.

## 8. Premier contrôle : est-ce que ça valait le coup ?

Même modèle que sous Windows (Hermes-4-14B, quantification Q4_K_M), même script
de mesure, même carte :

| Mesure | Windows 11 (09/09) | Rocky Linux 10 (10/10) |
|---|---|---|
| Lecture du prompt (4 000 tokens) | 3 344 tokens/s | **3 577 tokens/s** (+7 %) |
| Génération, une requête | 72 tokens/s | **78,5 tokens/s** (+9 %) |
| Génération, 4 requêtes simultanées (total) | — | **151 tokens/s** |
| Pic GPU | 64 °C, 284 W | 67 °C, 301 W |

Le gain sur une requête seule est modeste, et à prendre avec prudence : entre
les deux mesures, le système, le pilote **et** la version d'Ollama ont changé.
Le vrai changement, c'est le parallélisme : à quatre requêtes, chacune ralentit
(54 tokens/s), mais le total double. C'est exactement le profil d'un serveur qui
reçoit des requêtes de plusieurs clients.

Le prix à payer est la mémoire : 13,7 Go de VRAM occupés au lieu de 11,9 Go,
parce qu'Ollama réserve de la place pour quatre conversations à la fois. Et la
carte atteint sa limite de 300 W.

> **Piège vécu, côté mesure.** Ma deuxième série de mesures affichait une
> lecture du prompt à **277 000 tokens/s**, soixante-dix fois trop. Le modèle
> restait chargé entre deux séries, et mon script envoyait d'une série à
> l'autre exactement les mêmes prompts : Ollama les servait depuis son cache.
> Si un chiffre paraît trop beau, il faut chercher pourquoi. Le détail des
> mesures, et ce que ces chiffres valent face aux machines de référence du
> réseau, fera l'objet du prochain épisode.

## 9. Récapitulatif

- [ ] Lien PCIe vérifié en **x16** avant d'installer quoi que ce soit
- [ ] Système à jour, `kernel-devel` identique au noyau en cours d'exécution
- [ ] `nvidia-open` (modules ouverts), et non le pilote propriétaire
- [ ] Clé DKMS enrôlée au MOK Manager, module signé (`modinfo -F signer nvidia`)
- [ ] **Tous** les paquets du pilote verrouillés (`dnf versionlock list`)
- [ ] Docker sans groupe `docker`, SELinux toujours en mode Enforcing
- [ ] Script Ollama lu, version fixée, `PATH` restreint, `NUM_PARALLEL` vérifié dans le journal
- [ ] Ollama n'écoute que sur `127.0.0.1`

## 10. La suite

- **Épisode 3** : benchmarks en détail, test d'endurance de 24 heures, et
  checklist du jour J pour le testnet.

Mon DID : `did:key:z6MkgzG86nL4pgoytHsEUAshr24ByY8pvmRxYWFuVS2Y1DQi`
Épisode 1 : [Technocore et DID](https://www.myprivatelab.tech/flop/technocore-did)
Me suivre : [@bvivi57](https://x.com/bvivi57) — le projet : [@flop_labs](https://x.com/flop_labs)

### Références

- Dépôt CUDA de NVIDIA pour RHEL 10 : <https://developer.download.nvidia.com/compute/cuda/repos/rhel10/x86_64/>
- NVIDIA Container Toolkit : <https://github.com/NVIDIA/nvidia-container-toolkit>
- Docker CE pour RHEL : <https://docs.docker.com/engine/install/rhel/>
- Ollama : <https://github.com/ollama/ollama>
- Flop Network : <https://flop.finance>
- Mes outils : <https://github.com/bvivi57/flop>

*Toutes les commandes de cet article ont été exécutées sur Rocky Linux 10.2
entre le 16 septembre et le 10 octobre 2026.*
