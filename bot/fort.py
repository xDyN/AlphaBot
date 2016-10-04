# -*- coding: utf-8 -*-

import time

SPIN_REQUEST_RESULT_SUCCESS = 1
SPIN_REQUEST_RESULT_OUT_OF_RANGE = 2
SPIN_REQUEST_RESULT_IN_COOLDOWN_PERIOD = 3
SPIN_REQUEST_RESULT_INVENTORY_FULL = 4

class Fort(object):
	def __init__(self, fort, api):
		self.id = fort['id']
		self.lat = fort['latitude']
		self.lng = fort['longitude']
		self.name = None
		self.api = api

		self.detail()

	def detail(self):
		time.sleep(1)
		response_dict = self.api.fort_details(
			fort_id = self.id,
			latitude = self.lat,
			longitude = self.lng
		)['responses']['FORT_DETAILS']

		self.lat = response_dict['latitude'] 
		self.lng = response_dict['longitude']
		self.name = response_dict['name']



