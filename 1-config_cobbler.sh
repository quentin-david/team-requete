#!/bin/bash

# Installation des paquets necessaires sur le serveur de deploiement
# Parametrage de Cobbler
# Deploiement des conf Ansible de base

HYPERVISEUR_USER="pse32"

# supprime flag
rm -f prerequis.flag 2>/dev/null

# Cree et deploie la cle SSH sur l'hyperviseur
# si elle n'existe pas deja
if [[ ! -e ${HOME}/.ssh/id_rsa ]]; then
	ssh-keygen -t rsa -f ${HOME}/.ssh/id_rsa -P "" -q
	echo "#############  Veuillez rentrer le mot de passe pour l'hyperviseur ######################"
	ssh-copy-id ${HYPERVISEUR_USER}@192.168.122.1 
	echo "################  Merci  ########################################"
fi



# YUM
unset http_proxy
unset https_proxy
yum -y install cobbler cobbler-web dhcp debmirror
yum -y install python2-pip gcc python-dev libxml2-dev libxslt-dev gnome-python2-devel 
yum -y install libvirt-python libffi libffi-devel python-devel openssl-devel 

# PIP
export http_proxy="http://proxy.infra.dgfip:3128"
export https_proxy="http://proxy.infra.dgfip:3128"
pip install --upgrade pip
pip install ssh-paramiko
pip install pyyaml
#pip install libvirt-python

# Parametrage de Cobbler
cp ./templates/tftpd.template /etc/cobbler
cp ./templates/dhcp.template /etc/cobbler
sed -i s/"manage_dhcp: 0"/"manage_dhcp: 1"/g /etc/cobbler/settings
sed -i s/"pxe_just_once: 0"/"pxe_just_once: 1"/g /etc/cobbler/settings
COBBLER_IP=$(ip a | grep 192.168 | awk -P '{print $2}' | awk -F'/' '{print $1}')
sed -i s/"next_server: 127.0.0.1"/"next_server: ${COBBLER_IP}"/g /etc/cobbler/settings
sed -i s/"server: 127.0.0.1"/"server: ${COBBLER_IP}"/g /etc/cobbler/settings


# Lancement des services
systemctl enable cobblerd
systemctl enable rsyncd
systemctl enable httpd
systemctl enable xinetd
systemctl enable tftp

systemctl start cobblerd
systemctl start rsyncd
systemctl start httpd
systemctl start xinetd
systemctl start tftp

# Donnees Cobbler
cp ./templates/sample_perso.seed /var/lib/cobbler/kickstarts/
mount -o loop /var/tmp/ubuntu-16.04.2-server-amd64.iso /media
cobbler import --path=/media/ --name=ubuntu_server-x86_64
cobbler profile add --name=ubuntu_server-x86_64 --distro=ubuntu_server-x86_64 --kickstart=/var/lib/cobbler/kickstarts/sample_perso.seed
cobbler sync

# Creer flag
touch prerequis.flag

# reboot

# Installation des roles Ansible


