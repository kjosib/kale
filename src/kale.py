"""
I wanted to expose a SINGLE-THREADED WEB APPLICATION over HTTP to LOCALHOST ONLY.
Web application, because it's a comfortable style of working with data entry and navigation.
Single threaded, to support working well with SQLite, which doesn't play well with multi-threading,
and Windows, which is not particularly suited to a forking-model server.

Web browsers lately all expect to open multiple connections and might not send the first request on
the first connection. The Python Standard Library offers class "HttpServer", but as currently coded,
it only works properly when you're using a forking or threading mix-in. In sequential-service mode,
the standard library deadlocks (at least until the end user refreshes the browser a few times).

The essential problem is solved by setting a brief time-out on the first packet from the client.
If that time-out expires, the connection is closed and the server accepts the next caller, which
will generally have the request data from the browser. The server also only speaks HTTP/1.0 on
purpose: it guarantees all requests are served in a timely manner. There is zero packet latency
on localhost, so there's not a real performance drain here.

So long as I'm re-inventing the wheel, I might as well do it with the end in sight.
Therefore:

1. The server is a higher-order function: you pass in a handler function.
	The handler function must accept a `Request` object and return -- something: ideally
	a `Response` object, but in practice a suitable content body will do. There are some
	convenience methods for creating redirections, serving plain text, etc.

2. This means routing requests to different response methods is a separate problem.
	You could write a function which reads the path component of the `Request` URI to
	decide which of many sub-functions to call, and which bits of the path correspond
	to parameters, etc. In fact, any callable-object will do. In the abstract, we call
	that "routing a request" to the correct handler.

3. It's really annoying forgetting to commit-or-rollback a transaction in a handler.
	For some reason the changes appear fine locally, but nobody else sees anything
	except a locked database. Checking for this a simple matter by wrapping the root
	handler (application router) and taking corrective measures. (Roll back the
	transaction and return an error response maybe.)

4. The framework takes (some) pains to avoid excessive copying, drawing inspiration from the
	iolist facility in the Erlang ecosystem. Rather than building up a big string, supply
	a list of them, or a funny-shaped nest of them, etc. The rules are somewhat loose.

5. There's a simple HTML templating facility included: it will do the job without being
	accidentally quadratic. Much.

"""
import socket, urllib.parse, random, sys, html, traceback, re, operator, os
from typing import List, Tuple, Dict, Iterable, Match

class ProtocolError(Exception): """ The browser did something wrong. """

def serve_http(handle, *, port=8080):
	server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server.bind(('127.0.0.1', port))
	os.startfile('http://127.0.0.1:%d'%port)
	server.listen(1)
	print("Listening...")
	alive = True
	while alive:
		(client, address) = server.accept()
		print("Accepted...")
		client.settimeout(1)
		try: request = Request.from_reader(ClientReader(client))
		except socket.timeout: print("Timed out.")
		except ProtocolError as pe: print("Protocol Error", pe.args)
		else:
			try:
				response = handle(request)
				if not isinstance(response, Response): response = Response(response)
			except: response = Response.from_exception(request)
			if response.shut_down: alive = False
			try:
				client.sendall(response.content)
				print("Sent.")
			except:
				print("Failed to send.")
		client.shutdown(socket.SHUT_RDWR)
	print("Shutting Down.")

class ClientReader:
	"""
	This class exists because inbound requests are prone to
	antagonize the "file-like" abstraction.
	"""
	def __init__(self, client):
		self.client = client
		self.blob = client.recv(4096) # Try to pick up the entire request in one (notional) packet.
		self.start = 0
		self.waited = False
	
	def go_find(self, what:bytes) -> int:
		assert isinstance(what, bytes)
		try: return self.blob.index(what, self.start)
		except ValueError:
			if not self.waited: self.collect_more_packets()
			try: return self.blob.index(what, self.start)
			except ValueError: raise ProtocolError()
	
	def collect_more_packets(self):
		self.waited = True
		block = self.blob[self.start:]
		packets = [block]
		size = len(block)
		while True:
			try: block = self.client.recv(4096)
			except socket.timeout: break
			if block:
				packets.append(block)
				size += len(block)
			else: break
			if size > 1_000_000: raise ProtocolError()
		self.blob = b''.join(packets)
		self.start = 0
	
	def read_line_bytes(self) -> bytes:
		end = self.go_find(b'\r\n')
		start = self.start
		self.start = end + 2
		return self.blob[start:end]
	
	def read_count_bytes(self, count:int) -> bytes:
		end = self.start + count
		if end > len(self.blob): raise ProtocolError()
		block = self.blob[self.start:end]
		self.start = end
		return block
	
	def exhausted(self):
		return self.start == len(self.blob) and self.waited
	
	def read_rest(self):
		if not self.waited: self.collect_more_packets()
		result = self.blob[self.start:]
		self.start = len(self.blob)
		return result

class Bag:
	"""
	A structure designed to grapple with the vagaries of query parameters, request headers, etc.
	Acts like a dictionary of values, but also tracks lists of them.
	"""
	def __init__(self, pairs=None):
		self.single = {}
		self.multiple = {}
		if pairs is not None: self.update(pairs)
	def __getitem__(self, item): return self.single[item]
	def __setitem__(self, key, value):
		self.single[key] = value
		try: self.multiple[key].append(value)
		except KeyError: self.multiple[key] = [value]
	def __contains__(self, item): return item in self.single
	def update(self, pairs):
		if isinstance(pairs, dict): pairs = pairs.items()
		for key, value in pairs:
			self[key] = value
	def __str__(self): return str(self.multiple)
	def get(self, key, default=None): return self.single.get(key, default)
	def get_list(self, key): return self.multiple.get(key) or []
	def __delitem__(self, key):
		del self.single[key]
		del self.multiple[key]

class Request:
	"""
	The "request object" which a responder function can query.
	To promote testability, the constructor accepts native python data.
	The conversion from network binary blob happens in a static method that RETURNS a request.
	"""
	def __init__(self, command, uri, protocol, headers:Bag, payload):
		self.command = command
		self.uri = uri
		self.protocol = protocol
		self.headers = headers
		self.url = urllib.parse.urlparse(uri)
		self.GET = Bag(urllib.parse.parse_qsl(self.url.query, keep_blank_values=True))
		self.POST = Bag()
		if headers.get('content-type') == 'application/x-www-form-urlencoded':
			self.POST.update(urllib.parse.parse_qsl(str(payload, 'UTF-8'), keep_blank_values=True, max_num_fields=10_000))
		elif payload is not None:
			print("Command:", command, uri, protocol)
			print("Headers:", self.headers)
			print('GET:', self.GET)
			print("Payload:", payload)
	
	@staticmethod
	def from_reader(reader:ClientReader) -> "Request":
		command, uri, protocol = str(reader.read_line_bytes(), 'iso8859-1').split()
		headers = Bag()
		while not reader.exhausted():
			line = reader.read_line_bytes()
			if line:
				key, value = str(line, 'iso8859-1').split(': ',2)
				headers[key.lower()] = value
			else:
				break
		# If at this point a Content-Length header has arrived, that should tell the max number of bytes to expect as payload.
		if 'content-length' in headers:
			payload = reader.read_count_bytes(int(headers['content-length']))
		else:
			payload = None
		return Request(command, uri, protocol, headers, payload)

class Template:
	"""
	Any half-decent web framework needs to provide a cooperative templating system.
	This simple but effective approach cooperates with the iolist idea -- at least somewhat.
	
	Create a "Template" object from a string with {keyword} placeholders like this.
	For now, they should be strictly like identifiers. The object is then callable
	with said keyword parameters, and will put everything in the right places.
	Parameters will be entity-encoded unless they begin with a dot like {.this},
	in which case they're passed through as-is. Alternatively, like {this:how} means
	look up ':how' in the registry as a pre-processing step before html-encoding.
	"""
	PATTERN = re.compile(r'{(\.?)([_a-zA-Z]\w*)(:\w+)?}')
	REGISTRY = {}
	
	def __init__(self, text:str):
		self.items = []
		left = 0
		def literal(b:bytes): return lambda x:b
		def escape(keyword:str): return lambda x:html.escape(x[keyword])
		def preprocess(keyword:str, fn): return lambda x:html.escape(fn(x[keyword]))
		for match in Template.PATTERN.finditer(text):
			if left < match.start(): self.items.append(literal(bytes(text[left:match.start()], 'UTF-8')))
			if match.group(1): self.items.append(operator.itemgetter(match.group(2)))
			elif match.group(3): self.items.append(preprocess(match.group(2), Template.REGISTRY[match.group(3)]))
			else: self.items.append(escape(match.group(2)))
			left = match.end()
		if left < len(text): self.items.append(literal(bytes(text[left:], 'UTF-8')))
	
	def __call__(self, **kwargs):
		return [item(kwargs) for item in self.items]

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
		'Good Grief', 'Golly Gee Willikers', "Oh, Snot",
		'Great Googly Moogly', "Great Scott", 'Jeepers', "Heavens to Betsy", "Crikey",
		"Cheese and Rice all Friday", "Infernal Tarnation", "Mercy",
		'[Insert Curse Word Here]', 'Nuts', 'Oh Heavens', 'Rats', 'Wretch it all',
		'Whiskey Tango ....', 'Woe be unto me', 'Woe is me',
	]
	
	TEMPLATE_500 = Template("""
	<!DOCTYPE HTML> <html> <body>
	<h1>{curse}!</h1>
	<p>
		Something went wrong during: {command} <a href="{url}">{url}</a>
		Here's a stack trace. Perhaps you can send it to the responsible party.
	</p>
	<hr/>
	<pre style="background:red;color:white;padding:20px;font-weight:bold;font-size:20px">{trace}</pre>
	<pre style="background:black;color:green;padding:20px;font-size:20px">Python Version: {version}</pre>
	<hr/>
	</body> </html>
	""")
	
	def __init__(self, content, *, code:int=200, headers:Dict[str,str]=None, shut_down=False):
		def flatten(iolist):
			for item in iolist:
				if isinstance(item, str): yield bytes(item, 'UTF-8', errors='replace')
				elif isinstance(item, (bytes, bytearray)): yield item
				elif isinstance(item, dict): yield from flatten((key, b': ', value, b'\r\n') for key, value in item.items())
				elif isinstance(item, Iterable): yield from flatten(item)
				else: yield bytes(str(item))
		status_line = b"HTTP/1.0 %d %s\r\n"%(code, Response.REASON[code])
		if headers is None: headers = {}
		else: headers = {key.lower():str(value) for key, value in headers.items()}
		headers.setdefault('content-type', 'text/html')
		self.content = b''.join(flatten([status_line, headers, b'\r\n', content]))
		self.shut_down = bool(shut_down)
	
	@staticmethod
	def from_exception(request:Request) -> "Response":
		return Response(Response.TEMPLATE_500(
			command=request.command,
			url = request.url.geturl(),
			curse=random.choice(Response.MINCED_OATHS),
			version=str(sys.version),
			trace=traceback.format_exc(),
		), code=500)
	
	@staticmethod
	def redirect(url) -> "Response":
		return Response('', code=302, headers={'location':url})
	
	@staticmethod
	def plain_text(text) -> "Response":
		return Response(text, headers={'content-type':'text/plain'})
	
