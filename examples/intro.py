"""
This is your super-simple introductory example of how to get started.

The kale.py module must be in your PYTHONPATH environment variable.
That happens automatically if you use the demo.bat script at the
project root, or configure your IDE to consider ../src as "sources root".
"""

from kale import Request, Response, serve_http, Router

app = Router()

@app.function('/')
def trivial():
	global tally
	tally += 1
	assert tally % 5, "This is how errors/exceptions look."
	return [
		"Peace be with you.\r\n",
		"This is connection %d.\r\n"%tally,
		"As a demo of the error handling, every fifth hit to this page will fail an assertion.\r\n"
		"Try going to <a href=\"/add/5/7\">this link</a> to see some parameters in action."
	]
tally = 0


@app.function('add/*/*')
def add(a,b):
	a,b = float(a), float(b)
	return Response.plain_text(['The sum of <', a, '> and <', b, '> is <', a+b, '>.\r\nAlso, this page is plain text, not HTML.'])


serve_http(app)
