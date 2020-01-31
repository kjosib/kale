"""
This is your super-simple introductory example of how to get started.

The kale.py module must be in your PYTHONPATH environment variable.
That happens automatically if you use the demo.bat script at the
project root, or configure your IDE to consider ../src as "sources root".
"""

from kale import Request, Response, serve_http

tally = 0

def trivial(request:Request) -> Response:
	global tally
	tally += 1
	assert tally % 5, "This is how errors/exceptions look."
	return Response.plain_text([
		"Peace be with you.\r\n",
		"This is connection %d.\r\n"%tally,
		"Every fifth connection will show an error screen.\r\n"
	])


serve_http(trivial)
