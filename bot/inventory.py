# -*- coding: utf-8 -*-

import time
import json
import os

from bot.base_dir import _base_dir
from bot.item_list import Item
from bot.pokemon import Pokemon

ITEM_UNKNOWN = 0
ITEM_POKE_BALL = 1
ITEM_GREAT_BALL = 2
ITEM_ULTRA_BALL = 3
ITEM_MASTER_BALL = 4
ITEM_POTION = 101
ITEM_SUPER_POTION = 102
ITEM_HYPER_POTION = 103
ITEM_MAX_POTION = 104
ITEM_REVIVE = 201
ITEM_MAX_REVIVE = 202
ITEM_LUCKY_EGG = 301
ITEM_INCENSE_ORDINARY = 401
ITEM_INCENSE_SPICY = 402
ITEM_INCENSE_COOL = 403
ITEM_INCENSE_FLORAL = 404
ITEM_TROY_DISK = 501
ITEM_X_ATTACK = 602
ITEM_X_DEFENSE = 603
ITEM_X_MIRACLE = 604
ITEM_RAZZ_BERRY = 701
ITEM_BLUK_BERRY = 702
ITEM_NANAB_BERRY = 703
ITEM_WEPAR_BERRY = 704
ITEM_PINAP_BERRY = 705
ITEM_SPECIAL_CAMERA = 801
ITEM_INCUBATOR_BASIC_UNLIMITED = 901
ITEM_INCUBATOR_BASIC = 902
ITEM_POKEMON_STORAGE_UPGRADE = 1001
ITEM_ITEM_STORAGE_UPGRADE = 1002

class Inventory(object):
	def __init__(self, api, config, logger):
		self.api = api
		self.config = config
		self.logger = logger
		self.item_list = json.load(
			open(os.path.join(_base_dir, 'data', 'items.json'))
		)
		self.pokemon_list = json.load(
			open(os.path.join(_base_dir, 'data', 'pokemon.json'))
		)
		
		self.items = None
		self.pokemons = None
		self.exp = None
		self.next_exp = None
		self.level = None

		self.get_inventory()

	def get_inventory(self):
		time.sleep(1)
		inventorys = self.api.get_inventory()['responses']['GET_INVENTORY']['inventory_delta']['inventory_items']

		self.inventory_items(inventorys)
		self.inventory_pokemons(inventorys)
		self.inventory_stats(inventorys)

	def inventory_stats(self, inventorys):
		stats = {}

		for items in inventorys:
			stats = items.get('inventory_item_data', {}).get('player_stats', {})

			if stats:
				break

		self.exp = stats.get('experience', 0)
		self.next_exp = stats.get('next_level_xp', 0)
		self.level = stats.get('level', 0)

	def inventory_items(self, inventorys):
		items_stock = {x.value: 0 for x in list(Item)}

		for item in inventorys:
			item_dict = item.get('inventory_item_data', {}).get('item', {})
			item_count = item_dict.get('count')
			item_id = item_dict.get('item_id')

			if item_count and item_id:
				if item_id in items_stock:
					items_stock[item_id] = item_count

		self.items = items_stock

	def check_items(self):
		recycle_inventorys = []
		for item in self.config['item_limit']:
			item_id = int(self.item_list.keys()[self.item_list.values().index(item)])
			item_limit = self.config['item_limit'][item]
			item_count = self.items[item_id]

			if item_count and item_id and item_limit and item_count > item_limit:
				recycle_inventorys.append({
					'item_id': item_id,
					'count': item_count - item_limit
				})

				self.logger.info(	
					'Recycled: %s x%d',	
					self.item_list[str(item_id)],	
					item_count - item_limit	
				)

		self.recycle_items(recycle_inventorys)

	def recycle_items(self, items):
		if items:
			req = self.api.create_request()
			for item in items:
				self.items[item['item_id']] -= item['count']
				req.recycle_inventory_item(
					item_id = item['item_id'],
					count = item['count']
				)
			req.call()

	def inventory_pokemons(self, inventorys):
		pokemons_stock = []

		for pokemons in inventorys:
			pokemon_dict = pokemons.get('inventory_item_data', {}).get('pokemon_data', {})
			if pokemon_dict:
				pokemon = Pokemon(self.pokemon_list, pokemon_dict, None)
				if pokemon_dict.get('is_egg', None):
					pokemon.is_egg = True
				pokemons_stock.append(pokemon)

		self.pokemons = pokemons_stock

	def check_pokemons(self):
		pokemons = self.pokemons
		transfer_pokemons = []
		for pokemon in pokemons:
			if not pokemon.is_egg:
				transfer = self.pokemon_threshold(pokemon)

				if transfer:
					transfer_pokemons.append(pokemon)

		self.transfer_pokemons(transfer_pokemons)

	def transfer_pokemons(self, pokemons):
		if pokemons:
			req = self.api.create_request()
			for pokemon in pokemons:
				self.pokemons.remove(pokemon)
				req.release_pokemon(
					pokemon_id = pokemon.id
				)
			req.call()

	def pokemon_threshold(self, pokemon):
		if self.config['transfer_filter']['logic'] == 'or':
			if pokemon.cp < self.config['transfer_filter']['below_cp'] and pokemon.iv() < self.config['transfer_filter']['below_iv']:
				self.logger.info(
					'Tranferred %s [CP %s] [IV %s] [A/D/S %s]',
					pokemon.name,
					pokemon.cp,
					pokemon.iv(),
					pokemon.iv_display()
				)
				return True
		else:
			if pokemon.cp < self.config['transfer_filter']['below_cp'] or pokemon.iv() < self.config['transfer_filter']['below_iv']:
				self.logger.info(
					'Tranferred %s [CP %s] [IV %s] [A/D/S %s]',
					pokemon.name,
					pokemon.cp,
					pokemon.iv(),
					pokemon.iv_display()
				)
				return True
		return False