"""
This is your super-simple introductory example of how to get started.

The kale.py module must be in your PYTHONPATH environment variable.
That happens automatically if you use the demo.bat script at the
project root, or configure your IDE to consider ../src as "sources root".
"""

from kale import Response, serve_http, Router

# Any web application, you're going to be serving up different pages.
# You need a way to associate virtual-paths (in the URI hierarchy)
# with specific bits of code that you write. The kale.Router object
# is that way. It's basically the backbone of publishing your app.
app = Router()

# Great! We have a URI hierarchy. Now let's put a trivial page at
# the root of that hierarchy:
@app.function('/')
def trivial():
	"""
	Normally you would either return a full HTML document,
	or a kale.Response object. Note that a response can contain
	bytes, or strings, or a list of these, or a list of those...
	Basically anything iterable gets recursively flattened,
	automatically, somewhere on the way to the browser.
	Oh yes, UTF-8 everywhere.
	"""
	global tally
	tally += 1
	assert tally % 5, "This is how errors/exceptions look."
	return [
		"Peace be with you.\r\n",
		"This is connection %d to the root page.\r\n"%tally,
		"As a demo of the error handling, every fifth hit to this page will fail an assertion.\r\n"
		"Try going to <a href=\"/add/5/7\">this link</a> to see some parameters in action.\r\n"
		"Another approach to parameters is <a href=\"search?q=foo+bar+baz\">here</a>\r\n"
	]
tally = 0

# Aha! But what if we want our function to take parameters?
# There are a couple ways to achieve this. One handy method is
# wildcard paths. Look at this example:
@app.function('add/*/*')
def add(a,b):
	a,b = float(a), float(b)
	return Response.plain_text([
		'The sum of <', a, '> and <', b, '> is <', a+b,
		'>.\r\nAlso, this page is plain text, not HTML.',
	])

# You can also read query parameters using keyword-arguments. If there's
# a chance someone might not supply that argument, make sure to code
# a default value in your function definition. For example, the following
# exposes a (sham) search function.
@app.function('search')
def search(q=''):
	import html
	return """
	<html><body><h1>Bogus Search!</h1>
	<p>You searched: <code style="background:#cccccc">%s</code></p>
	<hr/>
	<p>This is just an example. No actual searching is performed.</p>
	</body></html>
	"""%html.escape(q)

# As you can imagine, this is just the tip of the iceberg. There's a lot more
# to see and do, but it will have to wait for another example program.

# Oh yes, before I forget:
# At the end of the main module, you're going to do something like this:

serve_http(app)
