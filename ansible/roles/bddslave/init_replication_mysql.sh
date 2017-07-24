#!/bin/bash
# --------------------------------------
# Initialisation de la réplication MySQL
# A exécuter sur le serveur esclave
# --------------------------------------
# Inits
# User MySQL esclave avec droits root
MYSQL_LUSER="administrateur"
MYSQL_LPASSWD="ertyerty"
# Serveur maitre
MYSQL_RHOST="192.168.200.30"
# User MySQL maitre avec droits root
MYSQL_RUSER="administrateur"
MYSQL_RPASSWD="ertyerty"
# User MySQL de réplication
MYSQL_REPL_USER="replication"
MYSQL_REPL_PASSWD="12345"
# Port SSH du serveur maitre
PSSH=22
# Bases à synchroniser
dbl="nextcloud"
 
echo "+++$(date) Debut $0"
 
# Saisie du mot de passe root local
#while [ ${#MYSQL_LPASSWD} -eq 0 ]; do
#    read -s -r -p "Mot de passe $MYSQL_LUSER MySQL local : " MYSQL_LPASSWD
#done
 
# Test de connexion à la base mysql locale
sql="USE mysql;"
req=`mysql -u $MYSQL_LUSER -p$MYSQL_LPASSWD -e "$sql"`
if [ $? -ne 0 ]; then
    echo -e "\n(E) $(date) Impossible de se connecter à la base locale mysql avec l'utilisateur $MYSQL_LUSER. Abandon du traitement"
    exit 1
else
    echo -e "\n(I) $(date) Connexion réussie à la base locale mysql."
fi
 
# Saisie du mot de passe root distant
#while [ ${#MYSQL_RPASSWD} -eq 0 ]; do
#    read -s -r -p "Mot de passe $MYSQL_RUSER MySQL $MYSQL_RHOST : " MYSQL_RPASSWD
#done
 
# Test de connexion à la base mysql distante
sql="USE mysql;"
req=`mysql --host $MYSQL_RHOST -u $MYSQL_RUSER -p$MYSQL_RPASSWD -e "$sql"`
if [ $? -ne 0 ]; then
    echo -e "\n(E) $(date) Impossible de se connecter à la base mysql de $MYSQL_RHOST avec l'utilisateur $MYSQL_RUSER. Abandon du traitement"
    exit 1
else
    echo -e "\n(I) $(date) Connexion réussie à la base mysql de $MYSQL_RHOST."
fi
 
# Verrouillage tables maitre
sql="FLUSH TABLES WITH READ LOCK;"
req=`mysql --host $MYSQL_RHOST -u $MYSQL_RUSER -p$MYSQL_RPASSWD -e "$sql"`
if [ $? -ne 0 ]; then
    echo -e "(E) $(date) Impossible de verrouiller les tables du serveur maitre. Abandon du traitement"
    exit 1
fi
 
# Récupération de l'état du maitre
sql="SHOW MASTER STATUS;"
req=($(mysql --host $MYSQL_RHOST -u $MYSQL_RUSER -p$MYSQL_RPASSWD -e "$sql" -B -s))
if [ $? -ne 0 ]; then
    echo -e "(E) $(date) Echec de récupération de l'état du serveur maitre. Abandon du traitement"
    exit 1
fi
MYSQL_LOGFILE=${req[0]}
MYSQL_OFFSET=${req[1]}
echo "Fichier de log courant sur $MYSQL_RHOST : $MYSQL_LOGFILE"
echo "Offset courant sur $MYSQL_RHOST : $MYSQL_OFFSET"
 
# Dump individuel des bases
for db in $dbl
do
    echo "$(date) Dump base $db en cours..."
    mysqldump --host $MYSQL_RHOST --user $MYSQL_RUSER --password=$MYSQL_RPASSWD $db | mysql --user $MYSQL_LUSER --password=$MYSQL_LPASSWD $db
    if [ $? -gt 0 ]; then
	echo "$(date) Erreur Dump base $db sur $MYSQL_RHOST"
    else
	echo "$(date) Base $db synchronisée"
    fi
done
 
# Déverrouillage tables maitre
sql="UNLOCK TABLES;"
req=`mysql --host $MYSQL_RHOST -u $MYSQL_RUSER -p$MYSQL_RPASSWD -e "$sql"`
if [ $? -ne 0 ]; then
    echo -e "(E) $(date) Impossible de déverrouiller les tables du serveur maitre."
fi
 
# Arret des threads esclaves
sql="STOP SLAVE;"
req=`mysql -u $MYSQL_LUSER -p$MYSQL_LPASSWD -e "$sql"`
if [ $? -ne 0 ]; then
    echo -e "(E) $(date) Impossible de mettre fin à l'esclavage :-("
    exit 1
fi
 
# Application des paramètres de réplication sur l'esclave
sql="CHANGE MASTER TO \
    MASTER_HOST='$MYSQL_RHOST', \
    MASTER_USER='$MYSQL_REPL_USER', \
    MASTER_PASSWORD='$MYSQL_REPL_PASSWD', \
    MASTER_LOG_FILE='$MYSQL_LOGFILE', \
    MASTER_LOG_POS=$MYSQL_OFFSET;"
req=`mysql -u $MYSQL_LUSER -p$MYSQL_LPASSWD -e "$sql"`
echo $req
if [ $? -ne 0 ]; then
    echo -e "(E) $(date) Impossible d'appliquer les paramètres de réplication."
    exit 1
fi
 
# Démarrage de la réplication
sql="START SLAVE;"
req=`mysql -u $MYSQL_LUSER -p$MYSQL_LPASSWD -e "$sql"`
if [ $? -ne 0 ]; then
    echo -e "(E) $(date) Impossible de démarrer la réplication."
fi
