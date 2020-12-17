"""
Time to split the implementation into a couple different (topical) files.
This one should be everything to do with what to send to the browser,
with the exception of actually sending it.
"""

__all__ = ['Response', ]

import random, sys, traceback
from typing import Iterable, Dict
from . import version, templates, requesting

class Response:
	"""
	Simple structure to organize the bits you need for a complete HTTP/1.0 response.
	"""
	REASON = {
		200: b"OK",
		201: b"Created",
		202: b"Accepted",
		204: b"No Content",
		301: b"Moved Permanently",
		302: b"Moved Temporarily",
		304: b"Not Modified",
		400: b"Bad Request",
		401: b"Unauthorized",
		403: b"Forbidden",
		404: b"Not Found",
		500: b"Internal Server Error",
		501: b"Not Implemented",
		502: b"Bad Gateway",
		503: b"Service Unavailable",
	}

	MINCED_OATHS = [
		'Ack', 'ARGH', 'Aw, SNAP', 'Blargh', 'Blasted Thing', 'Confound it',
		'Crud', 'Oh crud', 'Curses', 'Gack', 'Dag Blammit', 'Dag Nabbit',
		'Darkness Everywhere', 'Drat', 'Fiddlesticks', 'Flaming Flamingos',
		'Good Grief', 'Golly Gee Willikers', "Oh, Snot", "Oh, Sweet Cheese and Crackers",
		'Great Googly Moogly', "Great Scott", 'Jeepers', "Heavens to Betsy", "Crikey",
		"Cheese and Rice all Friday", "Infernal Tarnation", "Mercy",
		'[Insert Curse Word Here]', 'Nuts', 'Oh Heavens', 'Rats', 'Wretch it all',
		'Whiskey Tango ....', 'Woe be unto me', 'Woe is me',
	]

	TEMPLATE_GENERIC = templates.Template("""
	<!DOCTYPE html>
	<html><head><title>{title}</title></head>
	<body> <h1>{title}</h1>
	{.body}
	<hr/>
	<pre style="background:black;color:green;padding:20px;font-size:15px">Python Version: {python_version}\r\nKali version {kali_version}</pre>
	</body></html>
	""")

	TEMPLATE_GRIPE = templates.Template("""<p> Something went wrong during: {command} <a href="{url}">{url}</a> </p>""")

	TEMPLATE_STACK_TRACE = templates.Template("""
	<p> Here's a stack trace. Perhaps you can send it to the responsible party. </p>
	<pre style="background:red;color:white;padding:20px;font-weight:bold;font-size:15px">{trace}</pre>
	""")

	def __init__(self, content, *, code:int=200, headers:Dict[str,str]=None, shut_down=False):
		def flatten(iolist):
			for item in iolist:
				if isinstance(item, str): yield bytes(item, 'UTF-8', errors='replace')
				elif isinstance(item, (bytes, bytearray)): yield item
				elif isinstance(item, dict): yield from flatten((key, b': ', value, b'\r\n') for key, value in item.items())
				elif isinstance(item, Iterable): yield from flatten(item)
				else: yield bytes(str(item), 'UTF-8', errors='replace')
		status_line = b"HTTP/1.0 %d %s\r\n"%(code, Response.REASON[code])
		if headers is None: headers = {}
		else: headers = {key.lower():str(value) for key, value in headers.items()}
		headers.setdefault('content-type', 'text/html')
		self.content = b''.join(flatten([status_line, headers, b'\r\n', content]))
		self.code = code
		self.shut_down = bool(shut_down)

	@staticmethod
	def from_exception(request: requesting.Request) -> "Response":
		return Response.swear(request, Response.TEMPLATE_STACK_TRACE(trace=traceback.format_exc()))

	@staticmethod
	def swear(request: requesting.Request, detail, *, code=500) -> "Response":
		gripe = Response.TEMPLATE_GRIPE(command=request.command, url=request.url.geturl()),
		return Response.generic([gripe, detail], code=code, title=random.choice(Response.MINCED_OATHS)+'!')

	@staticmethod
	def redirect(url) -> "Response":
		return Response('', code=302, headers={'location':url})

	@staticmethod
	def plain_text(text) -> "Response":
		return Response(text, headers={'content-type':'text/plain'})

	@staticmethod
	def generic(body=None, *, title=None, code:int=200) -> "Response":
		return Response(Response.TEMPLATE_GENERIC(
			python_version=str(sys.version),
			kali_version=version.__version__,
			title=title or Response.REASON[code],
			body=body or "No further information.",
		), code=code)

