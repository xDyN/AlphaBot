# -*- coding: utf-8 -*- 

import os
import logging
import json
import time
import sys
import platform

from bot.base_dir import _base_dir
from bot import Bot

import bot.models

logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s [%(name)s] [%(levelname)s] %(message)s')
logger = logging.getLogger('init')
logger.setLevel(logging.INFO)

def main():
	logger.info('Alpha Bot v1.1')
	config = init_config()
	setup_logging(config)
	bot = Bot(config)
	bot.start()

def init_config():
	config_file = os.path.join(_base_dir, 'configs', 'config.json')

	config = {}

	if os.path.isfile(config_file):
		logger.info('Load config from /configs/config.json')
		with open(config_file, 'rb') as data:
			config.update(json.load(data))
	else:
		logger.error('No /configs/config.json or specified config')

	if config['auth_service'] not in ['ptc', 'google']:
		logging.error("Invalid Auth service specified! ('ptc' or 'google')")
		return None

	config.update({'encrypt_location': get_encrypt_lib()})

	return config

def get_encrypt_lib():
	if sys.platform == "win32" or sys.platform == "cygwin":
		if platform.architecture()[0] == '64bit':
			lib_name = "encrypt64bit.dll"
		else:
			lib_name = "encrypt32bit.dll"

	elif sys.platform == "darwin":
		lib_name = "libencrypt-osx-64.so"

	elif os.uname()[4].startswith("arm") and platform.architecture()[0] == '32bit':
		lib_name = "libencrypt-linux-arm-32.so"

	elif os.uname()[4].startswith("aarch64") and platform.architecture()[0] == '64bit':
		lib_name = "libencrypt-linux-arm-64.so"

	elif sys.platform.startswith('linux'):
		if "centos" in platform.platform():
			if platform.architecture()[0] == '64bit':
				lib_name = "libencrypt-centos-x86-64.so"
			else:
				lib_name = "libencrypt-linux-x86-32.so"
		else:
			if platform.architecture()[0] == '64bit':
				lib_name = "libencrypt-linux-x86-64.so"
			else:
				lib_name = "libencrypt-linux-x86-32.so"

	elif sys.platform.startswith('freebsd'):
		lib_name = "libencrypt-freebsd-64.so"

	lib_path = os.path.join(_base_dir, "libencrypt", lib_name)
	return lib_path

def setup_logging(config):
	logging.getLogger("requests").setLevel(logging.ERROR)
	logging.getLogger("websocket").setLevel(logging.ERROR)
	logging.getLogger("socketio").setLevel(logging.ERROR)
	logging.getLogger("engineio").setLevel(logging.ERROR)
	logging.getLogger("socketIO-client").setLevel(logging.ERROR)
	logging.getLogger("pgoapi").setLevel(logging.ERROR)
	logging.getLogger("rpc_api").setLevel(logging.ERROR)

	bot.models.init_db()
	bot.models.User.create_user(config['username'])


if __name__ == '__main__':
	main()