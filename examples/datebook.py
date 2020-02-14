"""
This example is a toy datebook application: You can use it to keep track of
contacts and appointments. It's meant to proof out the forms sub-library,
but it is (going to be) a reasonably-complete example.

It uses SQLite for data storage. In a complex application you might write
some query wrappers or use some pre-packaged ones so you get better errors.
"""
import sqlite3, pathlib, sys
from typing import Iterable
from kali import serve_http, Router, Request, Response, TemplateFolder, forms

# I want to use SQLite, and store my data in your home folder....
connection = sqlite3.connect(
	str(pathlib.Path.home() / 'datebook.sqlite'),
	detect_types=sqlite3.PARSE_DECLTYPES,
)
connection.row_factory = sqlite3.Row
cursor = connection.cursor()
def Q(text:str, params:Iterable=()):
	""" Stuff happens. I like to see what query failed, if it did. """
	try: return cursor.execute(text, params)
	except:
		print("Failing query was:", file=sys.stdout)
		print(text, file=sys.stdout)
		sys.stdout.flush()
		raise
	
Q('pragma foreign_keys = on') # Don't ask me why it's not the default.

# Set up the database if necessary.
with open(pathlib.Path(__file__).parent/"datebook.sql") as fh:
	for query in fh.read().split(';'):
		Q(query)

# Now, I want some basic page appearance templates:
tpl = TemplateFolder(pathlib.Path(__file__).parent/"datebook.tpl")

app = Router()

@app.function('/')
def dashboard():
	return tpl('page')(
		title="Dashboard",
		body="So I guess this would get a list of things coming up, in terms of appointments and tasks.",
	)

def transaction_wrapper(request:Request)->Response:
	try: response = app(request)
	finally:
		if connection.in_transaction:
			connection.rollback()
			return Response.swear(request, "I rolled back an uncommitted transaction.")
	return response

serve_http(tpl.wrap(transaction_wrapper))
