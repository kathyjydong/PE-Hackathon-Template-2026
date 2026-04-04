import os
import datetime
from peewee import (
    DatabaseProxy, Model, PostgresqlDatabase, 
    CharField, TextField, DateTimeField, ForeignKeyField
)

db = DatabaseProxy()

class BaseModel(Model):
    class Meta:
        database = db

# Class that creates the schema,, built off of the Pdf
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
    target_url = CharField(max_length=2048)
    short_code = CharField(max_length=50, unique=True)
    event = ForeignKeyField(Event, backref='urls', null=True, on_delete='CASCADE')
    created_by = ForeignKeyField(User, backref='created_urls', on_delete='CASCADE')
    created_at = DateTimeField(default=datetime.datetime.now)


def init_db(app):
    database = PostgresqlDatabase(
        os.environ.get("DATABASE_NAME", "hackathon_db"),
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", 5432)),
        user=os.environ.get("DATABASE_USER", "postgres"),
        password=os.environ.get("DATABASE_PASSWORD", "postgres"),
    )
    
    
    db.initialize(database)

    
    @app.before_request
    def _db_connect():
        db.connect(reuse_if_open=True)

    @app.teardown_appcontext
    def _db_close(exc):
        if not db.is_closed():
            db.close()
            
    
    db.create_tables([User, Event, Url])