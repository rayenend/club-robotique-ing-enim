Club Robotique ENIM — Install Party (version locale pour le jour J)
====================================================================

Ce dossier contient un site 100% autonome, a heberger depuis TON PC,
sans internet et sans compte Claude. Il fonctionne toute la journee
de l'evenement sur le reseau WiFi local.

CONTENU
-------
- server.py      -> le serveur (Python, deja installe sur la plupart des PC)
- index.html     -> le site (design noir/rouge, logo du club, animations)
- members.db     -> se cree automatiquement (base de donnees SQLite),
                    contient TOUTES les infos de tous les membres inscrits

PREREQUIS
---------
Python 3 doit etre installe sur le PC qui va heberger le site.
Verifier avec (dans un terminal / invite de commandes) :
    python3 --version
ou sur Windows parfois :
    python --version

Si Python n'est pas installe : https://www.python.org/downloads/
(cocher "Add Python to PATH" pendant l'installation sur Windows)

DEMARRAGE (le jour de l'evenement)
-----------------------------------
1. Ouvrir un terminal (ou invite de commandes) dans ce dossier.
2. Lancer :
       python3 server.py
   (sur Windows, si ca ne marche pas, essayer : python server.py)

3. Le terminal affiche deux adresses, par exemple :
       Sur ce PC          : http://localhost:8000
       Sur le reseau WiFi : http://192.168.1.42:8000

4. Sur TON PC (celui qui heberge) -> ouvrir http://localhost:8000
   Sur les PC/telephones DE TON EQUIPE (staff electrique, mecanique,
   membres) -> ouvrir http://192.168.1.42:8000 (remplacer par l'adresse
   affichee dans TON terminal) dans leur navigateur.

   IMPORTANT : tous les appareils doivent etre connectes au MEME
   reseau WiFi que le PC qui heberge le site (ex: le WiFi de la salle,
   ou un partage de connexion / hotspot depuis ton telephone).

5. Laisser le terminal ouvert pendant toute la duree de l'evenement.
   Fermer le terminal (ou Ctrl+C) arrete le site pour tout le monde.

TOUT EST PARTAGE EN DIRECT
---------------------------
Chaque check-in, chaque validation electrique/mecanique est enregistre
dans members.db et visible par tous les appareils connectes,
avec une actualisation automatique toutes les 2 secondes (pas besoin
de rafraichir la page).

ACCES DEPUIS UN AUTRE WIFI / DEPUIS INTERNET (pas seulement ton WiFi)
----------------------------------------------------------------------
Par defaut, le lien "reseau WiFi" (ex: http://192.168.1.42:8000)
fonctionne seulement pour les appareils connectes au MEME WiFi que
ton PC. Si tu veux que des gens sur un AUTRE reseau (autre WiFi, 4G,
autre batiment...) puissent aussi acceder au site, il faut un "tunnel"
qui donne une adresse publique https:// pointant vers ton PC. C'est
gratuit, ca ne demande pas de compte, et ca dure juste le temps que
tu le laisses ouvert (parfait pour un seul jour) :

  Option recommandee : Cloudflare Tunnel (cloudflared)
  1. Telecharger cloudflared :
     https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
  2. Lancer ton serveur normalement : python3 server.py
  3. Dans un DEUXIEME terminal, lancer :
     cloudflared tunnel --url http://localhost:8000
  4. cloudflared affiche une adresse du type :
     https://un-nom-au-hasard.trycloudflare.com
  5. C'est CETTE adresse que tu partages a tout le monde, peu importe
     leur reseau ou leur WiFi -- elle marche depuis n'importe ou avec
     une connexion internet.
  6. Fermer ce terminal arrete l'acces public (le site reste dispo
     en local sur ton WiFi tant que server.py tourne).

  Alternative : ngrok (necessite un compte gratuit sur ngrok.com)
     ngrok http 8000
     -> donne aussi un lien https://xxxx.ngrok-free.app

  Remarque securite : pendant que le tunnel est actif, N'IMPORTE QUI
  ayant le lien peut ouvrir le site et voir/ajouter des membres. Ne
  partage le lien qu'avec les personnes concernees par l'evenement,
  et ferme le tunnel une fois la journee terminee.

APRES L'EVENEMENT
------------------
Le fichier members.db contient la liste complete de tous les membres
inscrits (nom, telephone, email, filiere, PC, code, statut). C'est une
base SQLite standard -- tu peux l'ouvrir avec l'outil gratuit "DB
Browser for SQLite" (https://sqlitebrowser.org/) pour la consulter,
l'exporter en CSV/Excel, ou la requeter directement.

Pour repartir de zero un autre jour : supprimer members.db avant de
relancer le serveur (une nouvelle base vide sera recreee automatiquement).

FAIRE HEBERGER LE SITE EN PERMANENCE (toujours en ligne, pas seulement un jour)
--------------------------------------------------------------------------------
Le tunnel (section ci-dessus) marche seulement quand ton PC est allume et
connecte. Pour un site TOUJOURS en ligne, meme PC eteint, il faut un
vrai hebergeur cloud qui fait tourner server.py pour toi. Le code est
deja pret pour ca (il lit le port depuis la variable d'environnement
PORT, comme demandent ces plateformes).

Option recommandee : Render.com (gratuit pour demarrer)
  1. Creer un compte gratuit sur https://render.com
  2. Mettre ce dossier (server.py, index.html, Procfile) dans un depot
     GitHub (creer un compte GitHub si besoin, "New repository", puis
     glisser-deposer les fichiers via l'interface web GitHub).
  3. Sur Render : "New +" -> "Web Service" -> connecter ce depot GitHub.
  4. Regler : Runtime = Python 3, Build Command = (laisser vide),
     Start Command = python3 server.py
  5. Cliquer "Create Web Service". Render donne une adresse publique du
     type https://ton-club.onrender.com, active en permanence.

  A savoir sur le plan gratuit de Render :
  - Le service "s'endort" apres 15 minutes sans visite, et se reveille
    en 30-50 secondes a la prochaine visite (normal, pas un bug).
  - Le stockage est "ephemere" : members.db peut etre remis a zero a
    chaque redeploiement ou apres une longue inactivite.
  Pour que members.db ne soit JAMAIS perdu, il faut passer sur un plan
  payant (a partir de 7$/mois) et ajouter un "Persistent Disk" (Render
  -> onglet Disks -> mount path /var/data), puis definir la variable
  d'environnement DB_PATH=/var/data/members.db dans les reglages du
  service. C'est la seule difference a faire pour rendre les donnees
  permanentes.

Alternative : tout autre hebergeur qui accepte "Deploy from GitHub"
et un stockage persistant (Railway, Fly.io, PythonAnywhere, un VPS)
fonctionne aussi -- le point commun a verifier est toujours : port lu
depuis la variable PORT, et disque persistant pour members.db.

DEPANNAGE
---------
- "python3: command not found" -> installer Python (voir PREREQUIS).
- Les autres appareils n'arrivent pas a se connecter -> verifier que
  tout le monde est sur le meme WiFi, et que le pare-feu Windows/Mac
  n'a pas bloque Python (autoriser l'acces "reseau prive" si demande).
- Le port 8000 est deja utilise -> ouvrir server.py, changer la ligne
  "PORT = 8000" en un autre numero (ex: 8080), relancer.
