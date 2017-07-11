#!/usr/bin/python

import logging
import argparse
import paramiko
import os
import yaml
import libvirt
import time
import socket
import re

# Constantes
dieses = "###################################################"

# Parametrage du log
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('soclage')
handler = logging.FileHandler('soclage.log')
handler.setLevel(logging.INFO)
logger.addHandler(handler)

# Arg parser
description = """
Script de deploiement d'une infra Nextcloud
"""
parser = argparse.ArgumentParser(description=description)
parser.add_argument('config', help='Fichier de config YAML', type=str)
parser.add_argument('-p', '--printcmd', help='Print les commandes cobbler et virt-install', action='store_true')
parser.add_argument('--user', help="Utilisateur pour se connecter a l'hyperviseur", type=str)
parser.add_argument('--socler', help='Socler les machines', action='store_true')
parser.add_argument('--force', help='Supprime les entrees si elles existent', action='store_true')
parser.add_argument('--nics', help='Ajoute les cartes reseaux supplementaires', action='store_true')
parser.add_argument('--ansible', help='Deroule la configuration Ansible', action='store_true')
args = parser.parse_args()

"""
  Description des machines
"""
class Machine:
	definition_roles = {'web-p': 'Web primaire', 'web-s': 'Web secondaire', 'bdd-p': 'BDD primaire', 'bdd-b': 'BDD backup', 'ha-p': 'HAProxy primaire', 'ha-s': 'HAProxy secondaire', 'ldap-p': 'LDAP primaire', 'ldap-b': 'LDAP backup'}
	
	def __init__(self,name,ip_admin,role,disk=20,ram=512,vcpu=1,ip_frontend=None,ip_backend=None):
		self.name = name
		self.ip_admin = ip_admin
		self.role = role
		self.mac_admin = self.getRandomMac()
		self.disk = disk
		self.ram = ram
		self.vcpu = vcpu
		self.ip_frontend = ip_frontend
		self.ip_backend = ip_backend

	# Random Mac adress
	def getRandomMac(self):
		return '52:54:00:{}:{}:{}'.format(*[os.urandom(1).encode('hex') for i in range(3)])
		#return '52:54:00:12:e9:61'

	def getVirtInstallCmd(self):
		cmd = 'virt-install'
		cmd += ' --name='+self.name
		cmd += ' --ram='+str(self.ram)
		cmd += ' --mac='+self.mac_admin
		cmd += ' --vcpus='+str(self.vcpu)
		cmd += ' --disk path=/var/lib/libvirt/images/'+self.name+'.qcow,size='+str(self.disk)
		cmd += ' --virt-type kvm'
		cmd += ' --network network=default'
		cmd += ' --pxe'	
		return cmd

	def getVirtInstallDelete(self):
		cmd = 'virsh'
		cmd += ''
		return cmd

	def getCobblerAddCmd(self, edit=False):
		if edit:
			cmd = 'cobbler system edit'
		else:
			cmd = 'cobbler system add'
		cmd += ' --name='+self.name
		cmd += ' --hostname='+self.name
		cmd += '  --profile=ubuntu_server-x86_64'
		cmd += ' --interface=ens3'
		cmd += ' --ip-address='+self.ip_admin
		cmd += ' --subnet=255.255.255.0'
		cmd += ' --mac='+self.mac_admin
		cmd += ' --static=1'
		cmd += ' --gateway=192.168.122.1'
		return cmd

	# Rajoute les cartes reseaux supplementaires
	# si necessaire
	def addNetworkCard(self, network):
		conn = libvirt.open('qemu+ssh://'+args.user+'@192.168.1.1/system')
		xml_device = """
			<interface type='network'>
				<source network='"""+network+"""' />
				<model type='e1000' />
			</interface>
		 """
		if not re.search("source network='"+network+"'", conn.lookupByName(self.name).XMLDesc()):
			conn.lookupByName(self.name).attachDevice(xml_device)

	# Destroy the VM
	def deleteVm(self):
		conn = libvirt.open('qemu+ssh://'+args.user+'@192.168.1.1/system')
		#conn.lookupByName(self.name).destroy()
		#conn.lookupByName(self.name).undefine()


	# Create the VM
	def createVm(self):
		executeRemoteCommand('192.168.122.1',args.user, self.getVirtInstallCmd())
		# Verifie qu'elle est bien demarree, sinon on recommence
		time.sleep(2)
		if self.name not in getVmListe():
			executeRemoteCommand('192.168.122.1',args.user, self.getVirtInstallCmd())	
			time.sleep(2)


	# Verification des parametres de la machine (existence du reseau, champs manquants, etc)
	def checkParameters(self):
		if self.name=='' or self.ip_admin=='':
			return False
		return True


	def dump(self):
		print('Machine {} - {}').format(self.name, self.definition_roles[self.role])
		print('\t IP admin : {}, MAC : {}').format(self.ip_admin, self.mac_admin)
		if self.ip_frontend:
			print('\t IP frontend : {}').format(vm["ip_frontend"])
		if self.ip_backend:
			print('\t IP backend : {}').format(vm["ip_backend"])
		

	# Orchestration de la premiere phase (Cobbler, virt-install)
	# Avec verification de l'existant
	def socler(self):
		# Enregistrement dans Cobbler avec verification d'existence
		logger.info('Enregistrement de '+self.name+' dans Cobbler')
		if os.system(self.getCobblerAddCmd()) != 0:
			logger.warn('Entree existante dans Cobbler -> MAJ')
			os.system(self.getCobblerAddCmd(edit=True)) # si le systeme existe deja on l'edite
		os.system('cobbler sync >/dev/null 2>&1')
		time.sleep(1)
		# Creation et boot de la VM  => soclage avec seulement la carte d'admin
		# Verification de la presence de la VM
		if self.name in getVmListe():
			logger.info('VM '+self.name+' deja existante')
		else:
			logger.info('Ajout de la VM')
			self.createVm()
		

"""
 Description de la plateforme depuis un fichier YAML
"""
class Plateforme:
	definition_roles = {'web-p': 'Web primaire', 'web-s': 'Web secondaire', 'bdd-p': 'BDD primaire', 'bdd-b': 'BDD backup', 'ha-p': 'HAProxy primaire', 'ha-s': 'HAProxy secondaire', 'ldap-p': 'LDAP primaire', 'ldap-b': 'LDAP backup'}
	def __init__(self,config_file):
		if os.path.isfile(config_file):
			self.conf_map = yaml.load(open(config_file))
			self.liste_machines = self.conf_map["liste_machines"]
			self.date = self.conf_map["date"]
		else:
			self.liste_machines = None
	def dump(self):
		print(dieses+'\n\tDescription de la PF a deployer\n'+dieses)
		for vm in self.liste_machines:
			print('Serveur {} :').format(vm["name"])
			print('\t IP admin : {}, role : {}').format(vm["ip_admin"], self.definition_roles[vm["role"]])
		print(dieses)


# Execution d'une commande par SSH
def executeRemoteCommand(host,user,cmd, password=None, timeout=None):
	client = paramiko.SSHClient()
	client.load_system_host_keys()
	client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	if password == None:
		client.connect(host, username=user, look_for_keys=True, timeout=timeout)
	else:	
		client.connect(host, username=user, password=password, look_for_keys=False, timeout=timeout)
	stdin, stdout, stderr = client.exec_command(cmd)
	#logger.info('paramiko(stdin) : '+str(stdin))
	#return stdin
	return True


# verifie que le serveur de deploiement est lui-meme bien parametre
def checkPrerequisDeploiement():
	return os.path.isfile('prerequis.flag')


# Donne les liste des VMs existantes sur l'hyperviseur
def getVmListe():
	liste = []
	conn = libvirt.open('qemu+ssh://'+args.user+'@192.168.1.1/system')
	for dom in conn.listAllDomains():
		liste.append(dom.name())	
	return liste
	

"""
 #######################    MAIN     ###############################
"""
logger.info("Bienvenue sur l'assistant de soclage Nextcloud")

# Verification des prerequis du serveur de deploiement
if not checkPrerequisDeploiement():
	logger.warn(" Prerequis invalide !\n\t Executer d'abord le script 1-config_cobbler.sh")
	os.system('./1-config_cobbler.sh')
	logger.info("\t Prerequis OK")

plateforme = Plateforme(args.config) # Chargement de la conf YAML
plateforme.dump()

# Enregistrement dans Cobbler et creation de la VM
for vm in plateforme.liste_machines:
	logger.debug('\t Machine : '+vm["name"])
	# Creation des objets machine
	machine = Machine(name=vm["name"], ip_admin=vm["ip_admin"], role=vm["role"], ip_frontend=vm["ip_frontend"], ip_backend=["ip_backend"]);
	machine.dump()
	# Soclage des machines
	if args.socler:
		machine.socler()
		time.sleep(30)


# Dans un deuxieme temps, rajout des cartes reseaux supplementaires
if args.nics:
	logger.info('Deuxieme phase (Rajout NIC)')
	logger.info('Attente du reboot et rajout des cartes reseaux...')
	for vm in plateforme.liste_machines:
		machine=Machine(name=vm["name"], ip_admin=vm["ip_admin"], role=vm["role"], ip_frontend=vm["ip_frontend"], ip_backend=["ip_backend"]);
		reveille = 1
		while(reveille != 0):
			try:
				logger.info('Test ('+str(reveille)+') de vie de '+vm["name"])
				res = executeRemoteCommand(vm["ip_admin"], 'administrateur', 'uptime', 'ertyerty',5)
			except socket.timeout:
				res = None
				pass
			if res == None:
				time.sleep(30)
				reveille += 1
			else:
				reveille = 0
				logger.info('its alive !')
				if vm["ip_frontend"]:
					machine.addNetworkCard('frontend')
				if vm["ip_backend"]:
					machine.addNetworkCard('backend')
				time.sleep(5)
		logger.info('fin de boucle')


# Deploiement de la conf Ansible
if args.ansible:
	logger.info('Troisieme phase (Ansible)')
	logger.info('todo')

