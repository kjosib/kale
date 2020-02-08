"""
Before long, you'll want to access a database. And you'll want to make sure your
application doesn't accidentally leave the database hanging. Fortunately, there
is an easy solution.
"""
import sqlite3
from kali import Response, Router, serve_http

# Let's say you're delivering some sort of application experience over the
# localhost web, as `kali` is designed for. Somewhere near the top of your
# main program, you instantiate an application router as follows:
app = Router()

# For the sake of the example, let's have an in-memory SQLite database with
# a single table. In the real world, maybe you have several users connecting
# over a file-sharing network. (Maybe file permissions are access control?)

connection = sqlite3.connect(":memory:")
connection.execute("pragma foreign_keys=1")
connection.execute("create table simple (foo, bar)")
connection.commit()

# Now let's say your application is coming along nicely, but one of your
# service methods forgets to commit a transaction:

@app.function('/')
def forget_to_commit():
	assert not connection.in_transaction
	connection.execute("insert into simple values (1,2)")
	assert connection.in_transaction # i.e. we now have a pathological state.
	return "Misleading the user to wrongly believe that progress was saved."

# If, to start serving localhost-web, you'd simply written
#   serve_http(app)
# then you'd have a problem: Visiting the faulty function leaves the database
# locked for everyone else while showing you (and only you) a view of the
# data which is not actually saved.

# Since we know how to ask the database whether a transaction is in progress,
# it's possible to do a better job. Behold the application wrapper function:

def wrapped_application(request):
	""" Application wrapper-function that checks for left-open transactions. """
	# In practice you'd modify this according to your needs.
	try: response = app(request) # Note that the "app" is just a callable object.
	finally:
		if connection.in_transaction:
			connection.rollback()
			response = Response.swear(request, """
				<div style="color:red;background:yellow;padding:1em">
				<h2> The application forgot to commit a transaction. It's been rolled back. </h2>
				<p>
				Also, I meant to do that. I wanted to demonstrate catching a silent oversight
				before it blossoms into a nightmare tech support issue.
				Do please read the commentary in the source code. And then read
				<a href="https://tvtropes.org/pmwiki/pmwiki.php/Main/IMeantToDoThat">this.</a>
				</p>
				</div>
			""")
	return response

# At the end of the day,
serve_http(wrapped_application)

# Maybe you say "Hey man, this should all be configurable and stuff".
# You'd be absolutely right. There's a configuration language provided.
# It's called "Python".
