"""
Single-threaded web application service framework designed as an alternative to
ordinary desktop application development. See http://github.com/kjosib/kale
"""
import socket, urllib.parse, random, sys, html, traceback, re, operator, os
from typing import List, Tuple, Dict, Iterable, Match

STATUS_BYTES = {
}

class ProtocolError(Exception): """ The browser did something wrong. """

def serve_http(handle, *, port=8080, address='127.0.0.1', ):
	log_lines = {
		code: "<--  %d %s"%(code, str(reason, 'UTF-8', errors='replace'))
		for code, reason in Response.REASON.items()
	}
	def reply(response:Response):
		try:
			client.sendall(response.content)
			print(log_lines[response.code])
		except:
			print("Failed to send.")
	
	server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server.bind((address, port))
	os.startfile('http://%s:%d'%(address, port))
	server.listen(1)
	print("Listening...")
	alive = True
	while alive:
		(client, address) = server.accept()
		print("Accepted...")
		client.settimeout(1)
		try: request = Request.from_reader(ClientReader(client))
		except socket.timeout: print("Timed out.") # No reply; just hang up and move on.
		except ProtocolError as pe:
			print("Protocol Error", pe.args)
			reply(Response.generic(repr(pe.args) if pe.args else None, code=400))
		else:
			try:
				response = handle(request)
				if not isinstance(response, Response): response = Response(response)
				alive = not response.shut_down
			except:
				response = Response.from_exception(request)
			reply(response)
		client.shutdown(socket.SHUT_RDWR)
	print("Shutting Down.")

class ClientReader:
	"""
	This class exists because localhost connections tend to arrive out of sequence, so
	having a
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
	def items(self):
		""" Sort of pretend to act like a dictionary in this regard... """
		for k, vs in self.multiple.items():
			for v in vs: yield k, v
	def __bool__(self): return bool(self.single)

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
		self.path = self.url.path[1:].split('/') # Non-empty paths always start with a slash, so skip it.
		self.mount_depth = 0 # Useful for hierarchical applications.
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
		print(' -> ', command, uri)
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
	
	def normalize(self):
		path, normal = self.path, []
		for e in path:
			if e == '..': normal.pop()
			elif e in ('', '.'): pass
			else: normal.append(e)
		if path[-1] == '': normal.append('')
		if len(normal) < len(path):
			return Response.redirect(self.root_url(normal, self.GET or None))
	
	def root_url(self, path, query):
		qp = urllib.parse.quote_plus
		url = urllib.parse.quote('/'+'/'.join(path))
		if query is not None: url += '?'+'&'.join(qp(k)+'='+qp(v) for k,v in query.items())
		return url
		
	def app_url(self, path:List[str], query=None):
		return self.root_url(self.path[:self.mount_depth] + path, query)
	
	@staticmethod
	def __is_normal(path: List[str]):
		for i, elt in enumerate(path):
			if elt in ('', '.', '..'):
				return elt == '' and i == len(path) - 1
		return True
	
	@staticmethod
	def __normalize(path: List[str]):
		better = []
		for elt in path:
			if elt in ('', '.'): pass
			elif elt == '..':
				if len(better): better.pop()
			else: better.append(elt)
		if path[-1] in ('', '.') and better: better.append('')
		return '/' + '/'.join(better)


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
		def escape(keyword:str):
			def fn(x):
				item = x[keyword]
				if isinstance(item, str): item = html.escape(item)
				return item
			return fn
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
	
	TEMPLATE_GENERIC = Template("""
	<!DOCTYPE HTML>
	<html><head><title>{title}</title></head>
	<body> <h1>{title}!</h1>
	{.body}
	<hr/>
	<pre style="background:black;color:green;padding:20px;font-size:15px">Python Version: {version}\r\nKale version 0.0.1</pre>
	</body></html>
	""")
	
	TEMPLATE_GRIPE = Template("""<p> Something went wrong during: {command} <a href="{url}">{url}</a> </p>""")
	
	TEMPLATE_STACK_TRACE = Template("""
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
	def from_exception(request: Request) -> "Response":
		return Response.swear(request, Response.TEMPLATE_STACK_TRACE(trace=traceback.format_exc()))
	
	@staticmethod
	def swear(request: Request, detail, *, code=500) -> "Response":
		gripe = Response.TEMPLATE_GRIPE(command=request.command, url=request.url.geturl()),
		return Response.generic([gripe, detail], code=code, title=random.choice(Response.MINCED_OATHS))
	
	@staticmethod
	def redirect(url) -> "Response":
		return Response('', code=302, headers={'location':url})
	
	@staticmethod
	def plain_text(text) -> "Response":
		return Response(text, headers={'content-type':'text/plain'})
	
	@staticmethod
	def generic(body=None, *, title=None, code:int=200) -> "Response":
		return Response(Response.TEMPLATE_GENERIC(
			version=str(sys.version),
			title=title or Response.REASON[code],
			body=body or "No further information.",
		), code=code)


class Router:
	"""
	A simple, flexible, generic means of exposing functionality in a virtual
	path space with support for wildcard-mounts. The idea is you can use the
	wildcard to stand in for parameters to a function or class constructor.
	
	I've chosen the asterisk as wildcard because of long association. It's
	pretty much the only viable candidate.
	
	Internally, it's a prefix tree. Not that it's likely to matter, as the
	end user will be the performance bottleneck. But it's a fun exercise.
	"""
	
	WILDCARD = '*'
	
	def __init__(self): self.root = RouteNode()
	
	def __call__(self, request: Request):
		""" Route a request to the appropriate handler based on the deepest/longest match to a mount point. """
		normalize = request.normalize()
		if normalize is not None: return normalize
		
		# OK, that test passed. Now go find the most applicable handler.
		# A not-too-complicated back-tracking search. I anticipate that
		# real applications won't stress this too hard.
		path, node, i, found, best, backtrack = request.path, self.root, 0, None, -1, []
		while True:
			if node.handler is not None and i > best: found, best = node.handler, i
			if self.WILDCARD in node.kids: backtrack.append((node.kids[self.WILDCARD], i + 1))
			if i<len(path) and path[i] in node.kids: node, i = node.kids[path[i]], i + 1
			elif backtrack: node, i = backtrack.pop()
			elif found is None: return Response.generic(code=404)
			else:
				request.mount_depth = best # This is useful for handlers that resemble folders...
				return found(request)
	
	def __mount(self, path, handler):
		""" Internal method for insertion into virtual-path tree. """
		node = self.root
		for item in path: node = node.dig(item)
		assert node.handler is None
		node.handler = handler

	def function(self, where:str):
		"""
		Apply this parameterized decorator to publish functions.
		Use wildcards in the path to indicate positional arguments.
		Query arguments get translated to keyword parameters.
		A function will respond to GET requests, but anything else results
		in 501 Not Implemented. To support POST you'll need to write a class
		and decorate it with either @servlet('...') or @service('...').
		"""
		path, wild = self.__analyze_mountpoint(where)
		def decorate(fn):
			def proxy(request:Request):
				if len(request.path) == request.mount_depth and request.command == 'GET':
					return fn(*wild(request.path), **request.GET.single)
				else:
					return Response.generic(501)
			self.__mount(path, proxy)
			return fn
		return decorate
	
	def __analyze_mountpoint(self, where:str):
		""" A common factor to several publish-type decorator methods. """
		if where.startswith('/'): where = where[1:]
		path = where.split('/') # Guaranteed to have at least one component.
		assert all(path[:-1]), "Please do not put blank components in your virtual paths."
		wildcard_indices = tuple(i for i, p in enumerate(path) if p == self.WILDCARD)
		return path, lambda a:[a[i] for i in wildcard_indices]
	
	def servlet(self, where, allow_subpages=False):
		"""
		Wildcards in the path become positional arguments to the constructor
		for the class this expects to decorate. Then a do_GET or do_POST
		method gets called with the actual `Request` object as a parameter.
		"""
		path, wild = self.__analyze_mountpoint(where)
		def decorate(cls):
			assert isinstance(cls, type), type(cls)
			def servlet_handler(request:Request):
				if len(request.path) == request.mount_depth or allow_subpages:
					instance = cls(*wild(request.path))
					method = getattr(instance, 'do_' + request.command, None)
					if method is not None:
						return method(request)
				return Response.generic(501)
			self.__mount(path, servlet_handler)
			return cls
		return decorate
	
	def service(self, where):
		"""
		Similar to servlet, but one major difference: This expects
		to service an entire (virtual) folder using instance methods
		named like do_GET_this or do_POST_that.
		"""
		path, wild = self.__analyze_mountpoint(where)
		assert path[-1] == '', "Services mount at a folder, not a file. (End virtual-path with a slash.)"
		path.pop()
		def decorate(cls):
			assert isinstance(cls, type), type(cls)
			def service_handler(request:Request):
				appdepth = len(request.path) - request.mount_depth
				if appdepth == 1:
					instance = cls(*wild(request.path))
					name = request.path[request.mount_depth]
					method = getattr(instance, 'do_' + request.command+"_"+name, None)
					if method is not None:
						return method(request)
				elif appdepth == 0:
					return Response.redirect(request.app_url([''], request.GET))
				return Response.generic(501)
				
	
class RouteNode:
	def __init__(self):
		self.handler, self.kids = None, {}
	def dig(self, label):
		try: return self.kids[label]
		except KeyError:
			self.kids[label] = it = RouteNode()
			return it
