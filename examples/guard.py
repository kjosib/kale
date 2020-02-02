"""
Before long, you'll want to access a database. And you'll want to make sure your
application doesn't accidentally leave the database hanging. Fortunately, there
is an easy solution.
"""
import sqlite3
from kale import Response, Router, serve_http

connection = sqlite3.connect(":memory:")
connection.execute("pragma foreign_keys=1")
connection.execute("create table simple (foo, bar)")
connection.commit()

def guard_transactions(handler):
	"""
	This decorator shows one simple way to add a correctness criterion to the
	general act of servicing a request.
	"""
	def guard(request):
		try: response = handler(request)
		finally:
			if connection.in_transaction:
				connection.rollback()
				response = Response.swear(
					request,
					"""<h2 style="color:red;background:yellow;padding:1em">The application forgot to commit a transaction. It's been rolled back.</h2>"""
				)
		return response
	return guard

# The remainder of this is a simple demonstration. You should see the error about forgetting to commit.
app = Router()
@app.function('/')
def offend_the_guard():
	assert not connection.in_transaction
	connection.execute("insert into simple values (1,2)")
	assert connection.in_transaction

serve_http(guard_transactions(app))
