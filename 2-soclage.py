#!/usr/bin/python

################  Version 2 ###################

import logging
import argparse
import paramiko
import os
import yaml
import libvirt
import time
import socket
import re
import subprocess

# Constantes
dieses = "###########################################################"

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
parser.add_argument('--machine', nargs='?', help="Machine a resocler", type=str)
parser.add_argument('--socler', help='Socler les machines', action='store_true')
parser.add_argument('--check', help='Verifier les machines', action='store_true')
parser.add_argument('--force', help='Supprime les entrees si elles existent', action='store_true')
parser.add_argument('--ansible', help='Deroule la configuration Ansible', action='store_true')
args = parser.parse_args()

"""
  Description des machines
"""
class Machine:
	definition_roles = {'web-p': 'Web primaire', 'web-s': 'Web secondaire', 'bdd-p': 'BDD primaire', 'bdd-b': 'BDD backup', 'ha-p': 'HAProxy primaire', 'ha-s': 'HAProxy secondaire', 'ldap-p': 'LDAP primaire', 'ldap-b': 'LDAP backup', 'nfs-p': 'NFS primaire', 'infra-p': 'Serveur infra'}
	
	def __init__(self, name, ip, hyperviseur, role='small',disk=20,profil='small',plateforme=None, bridge=None):
		self.name = name
		self.role = role
		self.profil = plateforme.getProfil(profil)
		self.mac = self.getRandomMac()
		self.disk = disk
		self.hyperviseur = hyperviseur
		self.ram = self.profil['ram']
		self.vcpu = self.profil['cpu']
		self.ip = ip		
		self.plateforme = plateforme
		self.bridge = bridge


	def dump(self):
		print('Machine {} - {}').format(self.name, self.definition_roles[self.role])
		print('\t IP : {}, MAC : {}').format(self.ip, self.mac)
		print('\t Hyperviseur : {}, bridge: {}').format(self.hyperviseur, self.bridge)
		print('\t Profil VM : {}').format(self.profil)
		print('\t RAM : {} Mo - CPU : {}').format(self.ram, self.vcpu)


	# Random Mac adress
	def getRandomMac(self):
		return '52:54:00:{}:{}:{}'.format(*[os.urandom(1).encode('hex') for i in range(3)])

	
	# Commande de creation d'une VM avec virt-install
	def getVirtInstallCmd(self):
		cmd = 'virt-install'
		cmd += ' --name='+self.name
		cmd += ' --ram='+str(self.ram)
		cmd += ' --mac='+self.mac
		cmd += ' --vcpus='+str(self.vcpu)
		cmd += ' --disk path=/var/lib/libvirt/images/'+self.name+'.qcow2,size='+str(self.disk)
		cmd += ' --virt-type kvm'
		cmd += ' --network type=direct,source='+self.bridge+',source_mode=bridge'
		#cmd += ' --events on_poweroff=destroy,on_reboot=restart,on_crash=restart'
		#cmd += ' --events on_reboot=restart'
		cmd += ' --wait=-1'
		cmd += ' --noautoconsole'
		cmd += ' --pxe'
		return cmd

	# Verifie qu'une VM existe bien dans Libvirt
	def checkLibvirtSystemExist(self):
		conn = libvirt.open('qemu+ssh://'+args.user+'@'+self.hyperviseur+'/system')
		if self.name in conn.listAllDomains():
			return True	
		return False

	# Commande de creation/update d'un System dans Cobbler
	def getCobblerAddCmd(self, edit=False):
		if edit:
			cmd = 'cobbler system edit'
		else:
			cmd = 'cobbler system add'
		cmd += ' --name='+self.name
		cmd += ' --hostname='+self.name
		cmd += ' --profile='+self.plateforme.socle_profile
		cmd += ' --interface=ens3'
		cmd += ' --ip-address='+self.ip
		cmd += ' --subnet=255.255.255.0'
		cmd += ' --mac='+self.mac
		cmd += ' --static=1'
		cmd += ' --gateway=192.168.200.10'
		return cmd

	# Verifie qu'une entree existe bien dans Cobbler
	def checkCobblerSystemExist(self):
		try:
			retcode = subprocess.call("cobbler"+ " system report --name "+ self.name+" >/dev/null", shell=True)
			if retcode != 0: 
				return False
			else:
				return True
		except  OSError as e:
			print('error')	



	# Destroy the VM
	def deleteVm(self):
		conn = libvirt.open('qemu+ssh://'+args.user+'@192.168.1.1/system')
		#conn.lookupByName(self.name).destroy()
		#conn.lookupByName(self.name).undefine()


	# Create the VM
	def createVm(self):
		executeRemoteCommand(self.hyperviseur, args.user, self.getVirtInstallCmd())
		# Verifie qu'elle est bien demarree, sinon on recommence
		time.sleep(5)
		#if self.name not in getVmListe(hyperviseur):
		if not self.checkLibvirtSystemExist():
			executeRemoteCommand(self.hyperviseur, args.user, self.getVirtInstallCmd())	
			time.sleep(5)
	
	
	# Verification de l'etat de la machine
	def check(self):
		# Verification Cobbler
		if self.checkCobblerSystemExist():
			print('Cobbler OK')
		else:
			print("pas d'enregistrement Cobbler")
		# Verification Libvirt
		if self.checkLibvirtSystemExist():
			print('VM existante')
		else:
			print('pas de VM')

	"""
	 Orchestration de la premiere phase (Cobbler, virt-install)
	 Avec verification de l'existant
	"""
	def socler(self):
		# Enregistrement dans Cobbler avec verification d'existence
		logger.info('Enregistrement de '+self.name+' dans Cobbler')
		#if os.system(self.getCobblerAddCmd()) != 0:
			#logger.warn('Entree existante dans Cobbler -> MAJ')
			#os.system(self.getCobblerAddCmd(edit=True)) # si le systeme existe deja on l'edite
		if not self.checkCobblerSystemExist():
			os.system(self.getCobblerAddCmd())
		else:
			logger.warn('Entree existante dans Cobbler -> MAJ')
		
		os.system('cobbler sync >/dev/null 2>&1')
		time.sleep(10)
		# Creation et boot de la VM  => soclage avec seulement la carte d'admin
		# Verification de la presence de la VM
		#if self.name in getVmListe():
		if self.checkLibvirtSystemExist():
			logger.info('VM '+self.name+' deja existante')
		else:
			logger.info('Ajout de la VM')
			self.createVm()
			time.sleep(30)
		


"""
 Description de la plateforme depuis un fichier YAML
"""
class Plateforme:
	definition_roles = {'web-p': 'Web primaire', 'web-s': 'Web secondaire', 'bdd-p': 'BDD primaire', 'bdd-b': 'BDD backup', 'ha-p': 'HAProxy primaire', 'ha-s': 'HAProxy secondaire', 'ldap-p': 'LDAP primaire', 'ldap-b': 'LDAP backup', 'nfs-p': 'NFS primaire', 'infra-p': 'Serveur infra'}
	
	def __init__(self,config_file):
		if os.path.isfile(config_file):
			self.conf_map = yaml.load(open(config_file))
			if self.conf_map["liste_machines"] == None:
				logger.error('fichier parametre incomplet')
				exit(4)
			self.liste_machines = self.conf_map["liste_machines"]
			self.liste_profils = self.conf_map["liste_profils"]
			self.socle_profile = self.conf_map["socle_profile"]
			self.date = self.conf_map["date"]
		else:
			self.liste_machines = None

	def dump(self):
		print(dieses+'\n####\t  Description de la PF a deployer\n'+dieses)
		for vm in self.liste_machines:
			print('Serveur {} :'.format(vm["name"]))
			print('\t IP : {}, role : {}'.format(vm["ip"], self.definition_roles[vm["role"]]))
			print('\t IP interne : {}'.format(vm["ip"]))
			print('\t Profil VM : {}'.format(self.getProfil(vm["profil"])))
		print(dieses)

	# recupere les infos d'une machine a partir de son nom
	def getMachine(self, name):
		for vm in self.liste_machines:
			if vm["name"] == name:
				return vm
		return False

	# recupere le profil a partir de son nom
	def getProfil(self, name):
		for profil in self.liste_profils:
			if profil["name"] == name:
				return profil




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
	return stdout
	#return True


# verifie que le serveur de deploiement est lui-meme bien parametre
def checkPrerequisDeploiement():
	return os.path.isfile('prerequis.flag')



	

#######################    MAIN     ###############################
logger.info("Bienvenue sur l'assistant de soclage Nextcloud")


# Verification des prerequis du serveur de deploiement
if not checkPrerequisDeploiement():
	logger.warn(" Prerequis invalide !\n\t Executer d'abord le script 1-config_cobbler.sh")
	#os.system('./1-config_cobbler.sh')
	logger.info("\t Prerequis OK")

plateforme = Plateforme(args.config) # Chargement de la conf YAML
plateforme.dump()


# si l'argument --machine est rempli on ne prend que cette machine
if args.machine:
	liste_machines = []
	for machine in args.machine.split():
		if plateforme.getMachine(machine):
			liste_machines.append(plateforme.getMachine(machine))
		else:
			logger.error('Machine {} inconnue...'.format(machine))
	if len(liste_machines) == 0:
		print('Machine inconnue...')
		exit(5)
else:
	liste_machines = plateforme.liste_machines


# Enregistrement dans Cobbler et creation de la VM
for vm in liste_machines:
	# Creation des objets machine
	machine = Machine(name=vm["name"], ip=vm["ip"], hyperviseur=vm["hyperviseur"], disk=vm["disk"], role=vm["role"], profil=vm["profil"], plateforme=plateforme, bridge=vm["bridge"]);
	machine.dump()
	
	# Verification de la machine
	if args.check:
		machine.check()
	
	# Soclage des machines
	if args.socler:
		machine.socler()


	# Deploiement de la conf Ansible
	if args.ansible:
		logger.info('Troisieme phase (Ansible)')
		logger.info('todo')

