import datetime
import secrets
from peewee import CharField, TextField, DateTimeField, ForeignKeyField, DatabaseProxy, Model

# The proxy is the "phone line" that database.py will plug into later
db = DatabaseProxy()

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    username = CharField(max_length=50, unique=True, index=True)
    email = CharField(max_length=120, unique=True, index=True)
    password_hash = CharField(max_length=255)
    created_at = DateTimeField(default=datetime.datetime.now)

class Event(BaseModel):
    title = CharField(max_length=200, index=True)
    description = TextField(null=True)
    start_time = DateTimeField(default=datetime.datetime.now)
    host = ForeignKeyField(User, backref='events', on_delete='CASCADE')

class Url(BaseModel):
    # Renamed to original_url to match your routes logic
    original_url = CharField(max_length=2048)
    short_code = CharField(max_length=50, unique=True)
    # Optional fields from your original schema
    event = ForeignKeyField(Event, backref='urls', null=True, on_delete='CASCADE')
    created_by = ForeignKeyField(User, backref='created_urls', null=True, on_delete='CASCADE')
    created_at = DateTimeField(default=datetime.datetime.now)

    @classmethod
    def generate_code(cls):
        return secrets.token_urlsafe(6)

# This list tells the database which tables to create in Docker
ALL_MODELS = [User, Event, Url]