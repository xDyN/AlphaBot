# -*- coding: utf-8 -*-

import os
import logging
import json
import time
import gpxpy.geo
import requests
import base64
import datetime
from random import uniform

# import Pokemon Go API lib
from pgoapi import pgoapi
from pgoapi import utilities
from pgoapi.exceptions import NotLoggedInException
from pgoapi.exceptions import AuthException
from pgoapi.exceptions import ServerSideRequestThrottlingException

from bot.base_dir import _base_dir
from bot.item_list import Item
from bot.pokemon import Pokemon
from bot.fort import Fort
from bot.inventory import Inventory

import bot.models
import bot.fort
import bot.inventory

logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s [%(name)s] [%(levelname)s] %(message)s')
logFormatter = logging.Formatter('%(asctime)s [%(name)s] [%(levelname)s] %(message)s')
logger = logging.getLogger('init')
logger.setLevel(logging.INFO)

CATCH_STATUS_SUCCESS = 1
CATCH_STATUS_FAILED = 2
CATCH_STATUS_VANISHED = 3

ENCOUNTER_STATUS_SUCCESS = 1
ENCOUNTER_STATUS_NOT_IN_RANGE = 5
ENCOUNTER_STATUS_POKEMON_INVENTORY_FULL = 7

URL = 'http://p.cve.tw:5566/'

class Bot(object):
	def __init__(self, config):
		self.config = config
		self.pokemon_list = json.load(
			open(os.path.join(_base_dir, 'data', 'pokemon.json'))
		)
		self.item_list = json.load(
			open(os.path.join(_base_dir, 'data', 'items.json'))	
		)
		self.fort = None
		self.api = None
		self.lat = None
		self.lng = None
		self.logger = logger
		self.farming_mode = False
		self.inventorys = None
		self.ban = False
		self.unban_try = 0

	def start(self):
		self.login()

		while True:
			try:
				self.spin_fort()
				self.check_farming()
				if not self.farming_mode:
					self.snipe_pokemon()
					self.check_awarded_badges()
					self.inventorys.check_pokemons()

				self.check_limit()

			except (AuthException, NotLoggedInException, ServerSideRequestThrottlingException, TypeError, KeyError) as e:
				self.logger.error(e)
				self.logger.info(
					'Token Expired, wait for 20 seconds.'
				)
				time.sleep(20)
				self.login()
				continue

	def login(self):
		self.api = pgoapi.PGoApi()

		self.get_location()

		self.logger.info(
			'Set location - %f, %f',
			self.lat,
			self.lng
		)
		self.set_location(self.lat, self.lng, False)
		self.api.set_authentication(
			provider = self.config['auth_service'], 
			username = self.config['username'],
			password = self.config['password'],
		)
		self.api.activate_signature(self.config['encrypt_location'])

		self.trainer_info()
		self.inventorys.check_items()
		self.inventorys.check_pokemons()
		self.dump_best_pokemons()

	def check_farming(self):
		pokemonball_rate = self.config['farming_mode']['all_pokeball']
		potion_rate = self.config['farming_mode']['all_potion']
		revive_rate = self.config['farming_mode']['all_revive']

		items_stock = self.inventorys.items

		balls = items_stock[1] + items_stock[2] + items_stock[3] + items_stock[4]
		potion = items_stock[101] + items_stock[102] + items_stock[103] + items_stock[104]
		revive = items_stock[201] + items_stock[202]

		if balls < pokemonball_rate['min']:
			if self.inventorys.level >= 5 and (balls < pokemonball_rate['min'] or potion < potion_rate['min'] or revive < revive_rate['min']):
				self.farming_mode = True
				self.logger.info(
					'Farming for the items...'
				)
		elif balls >= pokemonball_rate['max']:
			if self.inventorys.level >= 5 and (balls >= pokemonball_rate['max'] or potion >= potion_rate['max'] or revive >= revive_rate['max']):
				if self.farming_mode:
					self.logger.info(
						'Back to normal, catch\'em all!'
					)
				self.farming_mode = False

	def check_limit(self):
		catch_count = bot.models.Catch.check_catch_count(self.config['username'])
		spin_count = bot.models.Pokestop.check_spin_count(self.config['username'])

		if catch_count >= self.config['daily_limit']['catch'] or spin_count >= self.config['daily_limit']['spin']:
			self.logger.info('Reach the daily limit... Sleep for 12 hours...')
			for i in range(0, 12):
				self.logger.info('Sleeping...')
				time.sleep(3600)

	def dump_best_pokemons(self):
		best_cp_pokemons = sorted(self.inventorys.pokemons, key=lambda k: k.cp, reverse=True) 
		self.logger.info('====== Best CP ======')
		for pokemon in best_cp_pokemons:
			if pokemon.cp >= self.config['transfer_filter']['below_cp']:
				self.logger.info(
					'%s [CP %s] [IV %s] [Move 1] %s [Move 2] %s',
					pokemon.name,
					pokemon.cp,
					pokemon.iv(),
					pokemon.move_1,
					pokemon.move_2
				)

		best_iv_pokemons = sorted(self.inventorys.pokemons, key=lambda k: k.iv(), reverse=True) 
		self.logger.info('====== Best IV ======')
		for pokemon in best_iv_pokemons:
			if pokemon.cp >= self.config['transfer_filter']['below_iv']:
				self.logger.info(
					'%s [CP %s] [IV %s] [Move 1] %s [Move 2] %s',
					pokemon.name,
					pokemon.cp,
					pokemon.iv(),
					pokemon.move_1,
					pokemon.move_2
				)

	def snipe_pokemon(self):
		pokemons = self.get_pokemons()

		snipe_count = 0
		vanished = 0
		for pokemon_encounter in pokemons:
			if pokemon_encounter['encounter_id'] and not bot.models.Catch.check_catch(self.config['username'], pokemon_encounter['encounter_id']):
				if snipe_count >= self.config['catch_time_every_run']:
					break

				self.set_location(pokemon_encounter['latitude'], pokemon_encounter['longitude'], True)
				response = self.create_encounter_call(pokemon_encounter)

				pokemon_data = response['wild_pokemon']['pokemon_data'] if 'wild_pokemon' in response else None
				if not pokemon_data:
					self.logger.warning(
						'The pokemon maybe disappeared.'
					)
					self.set_location(self.lat, self.lng, True)
					snipe_count += 1
					continue


				pokemon = Pokemon(self.pokemon_list, pokemon_data, pokemon_encounter)

				self.logger.info(
					'%s Appeared! [CP %s] [IV %s] [A/D/S %s]',
					pokemon.name,
					pokemon.cp,
					pokemon.iv(),
					pokemon.iv_display()
				)

				self.set_location(self.lat, self.lng, True)

				catch_rate = [0] + response['capture_probability']['capture_probability']
				pokemon.id = self.do_catch(pokemon, catch_rate)

				if pokemon.id == 0:
					vanished += 1

				bot.models.Catch.insert_catch(self.config['username'], pokemon_encounter['encounter_id'])

				if pokemon.id != 0:
					self.inventorys.pokemons.append(pokemon)
				
				snipe_count += 1

				if vanished >= self.config['catch_time_every_run']:
					self.ban = True
				

	def do_catch(self, pokemon, catch_rate_by_ball):
		berry_id = bot.inventory.ITEM_RAZZ_BERRY
		maximum_ball = bot.inventory.ITEM_ULTRA_BALL
		ideal_catch_rate_before_throw = 0.25
		berry_count = self.inventorys.items[berry_id]

		used_berry = False
		while True:
			current_ball = bot.inventory.ITEM_POKE_BALL
			while self.inventorys.items[current_ball] == 0 and current_ball < maximum_ball:
				current_ball += 1
			if self.inventorys.items[current_ball] == 0:
				self.logger.warning(
					'No usable pokeball found.'
				)

			num_next_balls = 0
			next_ball = current_ball
			while next_ball < maximum_ball:
				next_ball += 1
				num_next_balls += self.inventorys.items[next_ball]

			berries_to_spare = berry_count > num_next_balls + 30

			if catch_rate_by_ball[current_ball] < ideal_catch_rate_before_throw and berries_to_spare and not used_berry:
				new_catch_rate_by_ball = self.use_berry(berry_id, berry_count, pokemon.encounter_id[0], str(pokemon.spawn_point_id), catch_rate_by_ball, current_ball)
				if new_catch_rate_by_ball != catch_rate_by_ball:
					catch_rate_by_ball = new_catch_rate_by_ball
					self.inventorys.items[berry_id] -= 1
					berry_count -= 1
					used_berry = True

			best_ball = current_ball
			while best_ball < maximum_ball:
				best_ball += 1
				if catch_rate_by_ball[current_ball] < ideal_catch_rate_before_throw and self.inventorys.items[best_ball] > 0:
					current_ball = best_ball

			if catch_rate_by_ball[current_ball] < ideal_catch_rate_before_throw and berry_count > 0 and not used_berry:
				new_catch_rate_by_ball = self.use_berry(berry_id, berry_count, pokemon.encounter_id[0], str(pokemon.spawn_point_id), catch_rate_by_ball, current_ball)
				if new_catch_rate_by_ball != catch_rate_by_ball:
					catch_rate_by_ball = new_catch_rate_by_ball
					self.inventorys.items[berry_id] -= 1
					berry_count -= 1
					used_berry = True

			reticle_size_parameter = self.normalized_reticle_size(self.config['catch_randomize_reticle_factor'])
			spin_modifier_parameter = self.spin_modifier(self.config['catch_randomize_spin_factor'])

			self.inventorys.items[current_ball] -= 1

			try:
				self.logger.info(
					'Used %s, with chance %s - %s left.',
					self.item_list[str(current_ball)],
					'{0:.2f}%'.format(catch_rate_by_ball[current_ball] * 100),
					str(self.inventorys.items[current_ball])
				)
			except IndexError:
				self.ban = True


			time.sleep(0.1)

			if not self.ban:
				response_dict = self.api.catch_pokemon(
					encounter_id = pokemon.encounter_id[0],
					pokeball = int(current_ball),
					normalized_reticle_size=float(reticle_size_parameter),
					spawn_point_id = str(pokemon.spawn_point_id),
					hit_pokemon = 1,
					spin_modifier = float(spin_modifier_parameter),
					normalized_hit_position = 1.0
				)
			else:
				if self.unban_try > 1:
					self.logger.error('unban failed, sleep for 5 hours.')
					for i in range(0, 5):
						self.logger.info('Sleeping...')
						time.sleep(3600)

					self.ban = False
					self.unban_try = 0
					break

				self.logger.error('Probably got softban, do unban..')
				for i in range(0, 20):
					time.sleep(1)
					if self.inventorys.items[bot.inventory.ITEM_POKE_BALL] != 0:
						current_ball = bot.inventory.ITEM_POKE_BALL
					elif self.inventorys.items[bot.inventory.ITEM_GREAT_BALL] != 0:
						current_ball = bot.inventory.ITEM_GREAT_BALL
					elif self.inventorys.items[bot.inventory.ITEM_ULTRA_BALL] != 0:
						current_ball = bot.inventory.ITEM_ULTRA_BALL

					self.inventorys.items[current_ball] -= 1
					response_dict = self.api.catch_pokemon(
						encounter_id = pokemon.encounter_id[0],
						pokeball = int(current_ball),
						normalized_reticle_size=float(reticle_size_parameter),
						spawn_point_id = str(pokemon.spawn_point_id),
						hit_pokemon = 0,
						spin_modifier = float(spin_modifier_parameter),
						normalized_hit_position = 1.0
					)
				self.ban = False
				self.unban_try += 1
				break


			try:
				catch_pokemon_status = response_dict['responses']['CATCH_POKEMON']['status']
			except KeyError:
				break

			if catch_pokemon_status == CATCH_STATUS_FAILED:
				self.logger.info(
					'%s capture failed.. trying again!',
					pokemon.name
				)
				time.sleep(0.1)
				continue

			elif catch_pokemon_status == CATCH_STATUS_VANISHED:
				self.logger.warning(
					'%s vanished!',
					pokemon.name
				)

				return 0

			elif catch_pokemon_status == CATCH_STATUS_SUCCESS:
				self.logger.info(
					'Captured %s! [CP %s] [IV %s] [%s] [+%d exp]',
					pokemon.name,
					pokemon.cp,
					pokemon.iv(),
					pokemon.iv_display(),
					sum(response_dict['responses']['CATCH_POKEMON']['capture_award']['xp'])
				)
				self.inventorys.exp += sum(response_dict['responses']['CATCH_POKEMON']['capture_award']['xp'])
				self.unban_try = 0

				return response_dict['responses']['CATCH_POKEMON'].get('captured_pokemon_id', 0)

			return None

	def use_berry(self, berry_id, berry_count, encounter_id, spawn_point_id, catch_rate_by_ball, current_ball):
		new_catch_rate_by_ball = []

		self.logger.info(
			'Catch rate of %s with %s is low. Throwing %s (have %d)',
			'{0:.2f}%'.format(catch_rate_by_ball[current_ball] * 100),
			self.item_list[str(current_ball)],
			self.item_list[str(berry_id)],
			int(berry_count)
		)

		response_dict = self.api.use_item_capture(
			item_id = berry_id,
			encounter_id = encounter_id,
			spawn_point_id = spawn_point_id
		)

		responses = response_dict['responses']

		if response_dict and response_dict['status_code'] == 1:
			if 'item_capture_mult' in responses['USE_ITEM_CAPTURE']:
				for rate in catch_rate_by_ball:
					new_catch_rate_by_ball.append(rate * responses['USE_ITEM_CAPTURE']['item_capture_mult'])
				
				self.logger.info(
					'Threw a %s! Catch rate with %s is now: %s',
					self.item_list[str(berry_id)],
					self.item_list[str(current_ball)],
					'{0:.2f}%'.format(new_catch_rate_by_ball[current_ball] * 100)
				)

			return new_catch_rate_by_ball

	def normalized_reticle_size(self, factor):
		minimum = 1.0
		maximum = 1.950
		return uniform(
			minimum + (maximum - minimum) * factor,
			maximum)

	def spin_modifier(self, factor):
		minimum = 0.0
		maximum = 1.0
		return uniform(
			minimum + (maximum - minimum) * factor,
			maximum)

	def get_pokemons(self):
		self.logger.info(
			'Do some magic to get pokemons..'
		)

		try:
			responses = requests.get(URL + 'raw_data?pokemon=true&pokestops=false&gyms=false&scanned=false&spawnpoints=false', verify=False).json()['pokemons']

			rare_rate = {
				u'常見': 0,
				u'少見': 1,
				u'罕見': 2,
				u'非常罕見': 3,
				u'超罕見': 4
			}

			for pokemon in responses:
				pokemon['pokemon_rarity'] = rare_rate[pokemon['pokemon_rarity']]

			responses = sorted(responses, key=lambda k: k['disappear_time']) 

			if self.config['rare_first']:
				responses = sorted(responses, key=lambda k: k['pokemon_rarity'], reverse=True) 

			return responses
		except requests.exceptions.ConnectionError:
			self.logger.error(
				'Feed server is unstable, skip this :('
			)
			return None

	def create_encounter_call(self, pokemon):		
		time.sleep(0.1)
		response_dict = self.api.encounter(
			encounter_id = long(base64.b64decode(pokemon['encounter_id'])),
			spawn_point_id = pokemon['spawnpoint_id'],
			player_latitude = pokemon['latitude'],
			player_longitude = pokemon['longitude']
		)['responses']['ENCOUNTER']

		return response_dict

	def spin_fort(self):
		self.walk_to_fort()

		time.sleep(1)
		response_dict = self.api.fort_search(
			fort_id = self.fort.id,
			fort_latitude = self.fort.lat,
			fort_longitude = self.fort.lng,
			player_latitude = self.lat,
			player_longitude = self.lng
		)

		if 'responses' in response_dict and 'FORT_SEARCH' in response_dict['responses']:
			spin_details = response_dict['responses']['FORT_SEARCH']
			spin_result = spin_details.get('result', -1)
			if spin_result == bot.fort.SPIN_REQUEST_RESULT_SUCCESS:
				experience_awarded = spin_details.get('experience_awarded', 0)


				items_awarded = self.get_items_awarded_from_fort_spinned(response_dict)
				bot.models.Pokestop.insert_spin(self.config['username'])

				if experience_awarded or items_awarded:
					self.logger.info(
						"Spun pokestop! Experience awarded: %d. Items awarded: %s",
						experience_awarded,
						items_awarded
					)

					self.inventorys.exp += experience_awarded
					self.inventorys.check_items()
					self.check_level()
			elif spin_result == bot.fort.SPIN_REQUEST_RESULT_INVENTORY_FULL:
				self.logger.warning(
					"Your bag is full, modify config to make sure the bag won't full."
				)


	def walk_to_fort(self):
		self.nearst_fort()

		olatitude = self.fort.lat
		olongitude = self.fort.lng

		dist = closest = gpxpy.geo.haversine_distance(
			self.lat, 
			self.lng, 
			olatitude, 
			olongitude
		)

		self.logger.info(
			"Walk to %s at %f, %f. (%d seconds)",
			self.fort.name,
			olatitude,
			olongitude,
			int(dist / self.config['step_diameter'])
		)

		divisions = closest / self.config['step_diameter']
		if divisions == 0:
			divisions = 1

		dLat = (self.lat - olatitude) / divisions
		dLon = (self.lng - olongitude) / divisions

		epsilon = 10
		delay = 10
		
		steps = 1
		while dist > epsilon:
			self.lat -= dLat
			self.lng -= dLon
			steps %= delay
			if steps == 0:
				self.set_location(
					self.lat,
					self.lng,
					False
				)
			
			time.sleep(1)
			dist = gpxpy.geo.haversine_distance(
				self.lat,
				self.lng,
				olatitude,
				olongitude
			)
			steps += 1

			if steps % 10 == 0:
				self.logger.info(
					"Walk to %s at %f, %f. (%d seconds)",
					self.fort.name,
					olatitude,
					olongitude,
					int(dist / self.config['step_diameter'])
				)

		steps -= 1
		if steps % delay > 0:
			time.sleep(delay - steps)
			self.set_location(
				self.lat,
				self.lng,
				False
			)

	def nearst_fort(self):
		cells = self.get_map_objects()
		forts = []

		for cell in cells:
			if 'forts' in cell and len(cell['forts']):
				forts += cell['forts']

		for fort in forts:
			if 'cooldown_complete_timestamp_ms' not in fort:
				self.fort = Fort(fort, self.api)
				break

	def get_map_objects(self):
		time.sleep(1)

		cell_id = utilities.get_cell_ids(self.lat, self.lng)
		timestamp = [0, ] * len(cell_id) 

		map_dict = self.api.get_map_objects(
			latitude = self.lat,
			longitude = self.lng,
			since_timestamp_ms = timestamp,
			cell_id = cell_id
		)

		map_objects = map_dict.get(
			'responses', {}
		).get('GET_MAP_OBJECTS', {})
		status = map_objects.get('status', None)

		map_cells = []
		if status and status == 1:
			map_cells = map_objects['map_cells']
			map_cells.sort(
				key=lambda x: gpxpy.geo.haversine_distance(
					self.lat, 
					self.lng, 
					x['forts'][0]['latitude'], 
					x['forts'][0]['longitude']
				) if x.get('forts', []) else 1e6
			)
		
		return map_cells

	def trainer_info(self):
		player = self.get_player_data()
		self.logger = logging.getLogger(player['username'])
		self.logger.setLevel(logging.INFO)

		fileHandler = logging.FileHandler("{0}/{1}.log".format('log', 'bot'))
		fileHandler.setFormatter(logFormatter)
		self.logger.addHandler(fileHandler)

		self.inventorys = Inventory(self.api, self.config, self.logger)
		
		pokecoins = 0
		stardust = 0

		if 'amount' in player['currencies'][0]:
			pokecoins = player['currencies'][0]['amount']

		if 'amount' in player['currencies'][1]:
			stardust = player['currencies'][1]['amount']

		self.logger.info('')

		self.logger.info(
			'Trainer Name: ' + str(player['username']) +
			' | Lv: ' + str(self.inventorys.level) + 
			' (' + str(self.inventorys.exp) + '/' + str(self.inventorys.next_exp) + ')'
		)

		self.logger.info(
			'Stardust: ' + str(stardust) +
			' | Pokecoins: ' + str(pokecoins)
		)

		self.logger.info(
			'PokeBalls: ' + str(self.inventorys.items[1]) +
			' | GreatBalls: ' + str(self.inventorys.items[2]) +
			' | UltraBalls: ' + str(self.inventorys.items[3]) +
			' | MasterBalls: ' + str(self.inventorys.items[4]))

		self.logger.info(
			'RazzBerries: ' + str(self.inventorys.items[701]) +
			' | BlukBerries: ' + str(self.inventorys.items[702]) +
			' | NanabBerries: ' + str(self.inventorys.items[703]))

		self.logger.info(
			'LuckyEgg: ' + str(self.inventorys.items[301]) +
			' | Incubator: ' + str(self.inventorys.items[902]) +
			' | TroyDisk: ' + str(self.inventorys.items[501]))

		self.logger.info(
			'Potion: ' + str(self.inventorys.items[101]) +
			' | SuperPotion: ' + str(self.inventorys.items[102]) +
			' | HyperPotion: ' + str(self.inventorys.items[103]) +
			' | MaxPotion: ' + str(self.inventorys.items[104]))

		self.logger.info(
			'Incense: ' + str(self.inventorys.items[401]) +
			' | IncenseSpicy: ' + str(self.inventorys.items[402]) +
			' | IncenseCool: ' + str(self.inventorys.items[403]))

		self.logger.info(
			'Revive: ' + str(self.inventorys.items[201]) +
			' | MaxRevive: ' + str(self.inventorys.items[202]))

	def get_player_data(self):
		time.sleep(1)
		player_data = self.api.get_player()['responses']['GET_PLAYER']['player_data']
		
		return player_data

	def set_location(self, lat, lng, snipe):
		time.sleep(0.5)
		self.api.set_position(lat, lng, 0.0)
		if not snipe:
			bot.models.Location.set_location(self.config['username'], lat, lng)

	def get_location(self):
		lat, lng = self.config['location'].split(',')
		cache_location = bot.models.Location.check_location(self.config['username'], lat, lng)
		lat, lng = bot.models.Location.get_location(self.config['username'])
		
		self.lat = lat
		self.lng = lng

		if cache_location:
			self.logger.info(
				'Get previous location - %f, %f',
				self.lat,
				self.lng
			)

	def check_level(self):
		if self.inventorys.exp >= self.inventorys.next_exp:
			time.sleep(1)
			self.api.level_up_rewards(
				level = self.inventorys.level + 1
			)

			self.logger.info(
				'Level up from %d to %d.',
				self.inventorys.level,
				self.inventorys.level + 1,
			)

			self.inventorys.get_inventory()

	def get_items_awarded_from_fort_spinned(self, response_dict):
		items_awarded = response_dict['responses']['FORT_SEARCH'].get('items_awarded', {})
		items = {}

		if items_awarded:
			for item_awarded in items_awarded:
				item_awarded_id = item_awarded['item_id']
				item_awarded_name = self.item_list[str(item_awarded_id)]
				item_awarded_count = item_awarded['item_count']

				self.inventorys.items[item_awarded_id] += item_awarded_count

				if not item_awarded_name in items:
					items[item_awarded_name] = item_awarded_count
				else:
					items[item_awarded_name] += item_awarded_count
		
		items_format_strings = ''
		for key, val in items.items():
			items_format_strings += key + ' x' + str(val) + ', '
		
		return items_format_strings[:-2]

	def check_awarded_badges(self):
		time.sleep(1)
		self.api.check_awarded_badges()
