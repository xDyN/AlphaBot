from peewee import *
from playhouse.sqlite_ext import SqliteExtDatabase
import datetime

db_schema_version = 1
db = SqliteExtDatabase('bot.db')

class BaseModel(Model):
	class Meta:
		database = db

class User(BaseModel):
	username = CharField(unique=True)

	@staticmethod
	def create_user(name):
		try:
			user = User.create(username=name)
			Location.create(user=user, start_lat=0, start_lng=0, lat=0, lng=0)
		except IntegrityError:
			None


class Location(BaseModel):
	user = ForeignKeyField(User, related_name='locations', primary_key=True)
	start_lat = DoubleField()
	start_lng = DoubleField()
	lat = DoubleField()
	lng = DoubleField()

	@staticmethod
	def check_location(name, lat, lng):
		locations = Location.select().where(
			Location.user == User.select().where(User.username == name), 
			Location.start_lat == lat,
			Location.start_lng == lng
		).count()

		if locations == 0:
			q = Location.update(
					start_lat = lat,
					start_lng = lng,
					lat = lat,
					lng = lng,
				).where(
					Location.user == User.select().where(User.username == name)
				)
			q.execute()

			return False

		return True

	@staticmethod
	def get_location(name):
		locations = Location.select().where(
			Location.user == User.select().where(User.username == name)
		).get()

		return locations.lat, locations.lng

	@staticmethod
	def set_location(name, lat, lng):
		q = Location.update(
				lat = lat,
				lng = lng,
			).where(
				Location.user == User.select().where(User.username == name)
			)
		q.execute()


class Catch(BaseModel):
	user = ForeignKeyField(User, related_name='catchs')
	encounter_id = CharField(max_length=50)
	created_date = DateTimeField(default=datetime.datetime.now)

	@staticmethod
	def insert_catch(name, encounter_id):
		Catch.create(
			user = User.select().where(User.username == name),
			encounter_id = encounter_id
		)

	@staticmethod
	def check_catch(name, encounter_id):
		catchs = Catch.select().where(
			Catch.user == User.select().where(User.username == name),
			Catch.encounter_id == encounter_id
		).count()

		if catchs == 0:
			return False
		return True

	@staticmethod
	def check_catch_count(name):
		q = Catch.delete().where(
			Catch.user == User.select().where(User.username == name),
			Catch.created_date < datetime.datetime.now() - datetime.timedelta(hours=12)
		)
		q.execute()

		catchs = Catch.select().where(
			Catch.user == User.select().where(User.username == name)
		).count()

		return catchs

class Pokestop(BaseModel):
	user = ForeignKeyField(User, related_name='stops')
	created_date = DateTimeField(default=datetime.datetime.now)

	@staticmethod
	def insert_spin(name):
		Pokestop.create(
			user = User.select().where(User.username == name),
		)

	@staticmethod
	def check_spin_count(name):
		q = Pokestop.delete().where(
			Pokestop.user == User.select().where(User.username == name),
			Pokestop.created_date < datetime.datetime.now() - datetime.timedelta(hours=12)
		)
		q.execute()

		spins = Pokestop.select().where(
			Pokestop.user == User.select().where(User.username == name)
		).count()

		return spins
			
def init_db():
	db.connect()
	db.create_tables([User, Location, Catch, Pokestop], safe=True)
	db.close()
