"""
Single-threaded web application service framework designed as an alternative to
ordinary desktop application development. See http://github.com/kjosib/kali
"""

__all__ = [
	'serve_http', 'Request', 'Template', 'Response', 'Router', 'StaticFolder',
	'TemplateFolder', 'Servlet', 'FileUpload',
]

import socket, urllib.parse, random, sys, html, traceback, re, operator, os, pathlib, logging
from typing import List, Dict, Iterable, Callable, Optional, Mapping, NamedTuple
import traceback
from . import version

HTTP_DEFAULT_ENCODING = 'iso8859-1'
HTTP_EOL = b'\r\n'
LEN_HTTP_EOL = len(HTTP_EOL)

class ProtocolError(Exception): """ The browser did something wrong. """

log = logging.getLogger('kali')
log.setLevel(logging.INFO)

def serve_http(handle, *, port=8080, address='127.0.0.1', start:Optional[str]='', timeout=1):
	"""
	This is the main-loop entry point for kali.
	:param handle: function from `Request` to `Response` or suitable page data.
	:param port: self-explanatory
	:param address: In case you desperately want to serve remote traffic, change this.
	:param start: Where in the hierarchy shall we open a browser? If None, don't.
            NB: If something goes wrong binding a socket, we shan't open a browser...
	:return: only if the handler ever sets the `shutdown` flag in a response.
	"""
	log_lines = {
		code: "<--  %d %s"%(code, str(reason, 'UTF-8', errors='replace'))
		for code, reason in Response.REASON.items()
	}
	def reply(response:Response):
		try: client.sendall(response.content)
		except: log.exception("Failed to send.")
		else: log.info(log_lines[response.code])
	
	server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server.bind((address, port))
	server.listen(1)
	if start is not None:
		os.startfile('http://%s:%d/%s'%(address, port, start.lstrip('/')))
	log.info("Listening...")
	alive = True
	while alive:
		(client, address) = server.accept()
		log.info("Accepted...")
		try: request = Request.from_reader(ClientReader(client, timeout=timeout))
		except socket.timeout: log.info("Timed out.") # No reply; just hang up and move on.
		except ProtocolError as pe:
			log.warning("Protocol Error: %s %s", pe, traceback.format_exc())
			reply(Response.generic(code=400))
		else:
			try:
				response = handle(request)
				if not isinstance(response, Response): response = Response(response)
				alive = not response.shut_down
			except:
				log.exception("During %s %s", request.command, request.uri)
				response = Response.from_exception(request)
			reply(response)
		try: client.shutdown(socket.SHUT_RDWR)
		except OSError: pass
	log.info("Shutting Down.")

class ClientReader:
	"""
	This class exists to encapsulate specific phases of reading request data
	from a socket in light of the particular difficulties posed by the
	requirement to operate with a single thread.
	"""
	def __init__(self, client, timeout):
		self.client = client
		client.settimeout(timeout)
		self.blob = self.get_one_packet() # Try to pick up the entire request in one (notional) packet.
		self.start = 0
		self.waited = False

	def get_one_packet(self) -> bytes:
		packet = self.client.recv(4096)
		return packet

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
			try: block = self.get_one_packet()
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
		log.debug(str(self.blob[start:end], HTTP_DEFAULT_ENCODING))
		return self.blob[start:end]
	
	def read_count_bytes(self, count:int) -> bytes:
		end = self.start + count
		if end > len(self.blob):
			if not self.waited:
				self.collect_more_packets()
				end = count
			if end > len(self.blob): raise ProtocolError(end, len(self.blob))
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
	def __init__(self, command, uri, protocol, headers:Bag, payload:bytes):
		self.command = command
		self.uri = uri
		self.protocol = protocol
		self.headers = headers
		self.url = urllib.parse.urlparse(uri)
		self.path = urllib.parse.unquote(self.url.path)[1:].split('/') # Non-empty paths always start with a slash, so skip it.
		# The following bits collaborate with the Router class to provide a semblance
		# of a virtual path hierarchy into which you can mount functionality.
		self.mount_depth = 0 # How deep is the root of the mount which is handling this request?
		self.args = () # Actual parameters to mount-path wildcards. Filled in for Router.delegate(...) mounts.
		self.GET = Bag(urllib.parse.parse_qsl(self.url.query, keep_blank_values=True))
		self.POST = Bag()
		content_type = headers.get('content-type')
		if content_type == 'application/x-www-form-urlencoded':
			self.POST.update(urllib.parse.parse_qsl(str(payload, 'UTF-8'), keep_blank_values=True))
		elif content_type is not None and content_type.startswith("multipart/form-data;"):
			try: boundary_parameter = bytes(content_type.split('boundary=')[1], HTTP_DEFAULT_ENCODING)
			except: raise ProtocolError()
			self.POST.update(analyze_multipart_form_data(boundary_parameter, payload))
			pass
		elif payload:
			# TODO: If the browser sends a payload of any other sort, I'd like to figure out how to read it.
			log.warning("content-type was %s", headers.get('content-type'))
			log.warning("Command: %s %s %s", command, uri, protocol)
			log.warning("Payload: %r", payload)
	
	@staticmethod
	def from_reader(reader:ClientReader) -> "Request":
		command, uri, protocol = str(reader.read_line_bytes(), HTTP_DEFAULT_ENCODING).split()
		log.info(' -> %s %s', command, uri)
		headers = Bag()
		while not reader.exhausted():
			line = reader.read_line_bytes()
			if line:
				try:
					key, value = str(line, HTTP_DEFAULT_ENCODING).split(': ', 2)
					headers[key.lower()] = value
				except:
					log.warning("Bogus Request Line: %r", line)
					raise
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
	
	def root_url(self, path, query=None):
		qp = urllib.parse.quote_plus
		url = urllib.parse.quote('/'+'/'.join(path))
		if query: url += '?'+'&'.join(qp(k)+'='+qp(v) for k,v in query.items())
		return url
		
	def app_url(self, path:List[str], query=None):
		return self.root_url(self.path[:self.mount_depth] + path, query)
	
	def path_suffix(self) -> List[str]:
		return self.path[self.mount_depth:]
	
	def has_suffix(self) -> bool:
		" Does this Request have additional path components after the mount? "
		return self.mount_depth < len(self.path)
	
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


def analyze_multipart_form_data(boundary_parameter, payload:bytes):
	"""
	See https://tools.ietf.org/html/rfc7578 to understand what this is doing.
	And yes it might be simpler to exploit a MIME library.
	The RFC is what I actually found when looking into this.
	:yield: pairs of key/value, where the values may be file uploads.
	"""
	for part in payload.split(b'--' + boundary_parameter):
		if not part: continue
		if part == b'--'+HTTP_EOL: continue
		if not part.startswith(HTTP_EOL): raise ProtocolError
		if not part.endswith(HTTP_EOL): raise ProtocolError
		yield analyze_single_part(part[LEN_HTTP_EOL:-LEN_HTTP_EOL])

def analyze_single_part(part:bytes):
	"""
	Here we have a similar problem to the original ClientReader, but now it's
	line-at-a-time.
	"""
	head, body = part.split(HTTP_EOL+HTTP_EOL, 1)
	name, filename, content_type = None, None, 'text/plain'
	for line in head.split(HTTP_EOL):
		k,v = str(line, HTTP_DEFAULT_ENCODING).split(': ', 1)
		if k == 'Content-Disposition': name, filename = analyze_disposition(v)
		elif k == 'Content-Type': content_type = v
		else: raise ProtocolError(k)
	if filename is None: return name, str(body, HTTP_DEFAULT_ENCODING)
	else: return name, FileUpload(filename, content_type, body)

def analyze_disposition(disposition:str):
	m = re.fullmatch(r'form-data; name="([^"]*)"; filename="([^"]*)"', disposition)
	if m: return m.groups()
	m = re.fullmatch(r'form-data; name="([^"]*)"', disposition)
	if m: return m.group(1), None
	log.warning("Odd Content-Disposition: %s", disposition)
	raise ProtocolError()

class FileUpload(NamedTuple):
	filename: str
	content_type: str
	content: bytes

class AbstractTemplate:
	"""
	"Acts like a template" means a callable object that turns
	keyword parameters into an IoList.
	"""
	
	def __call__(self, **kwargs): return self.sub(kwargs)
	
	def sub(self, parameters:Mapping): raise NotImplementedError(type(self))
	
	def assembly(self, **kwargs) -> "SubAssembly":
		"""
		Templates are a lot like functions. You should be able to snap them
		together like legos into larger, more powerful templates. One way
		would be to write ordinary Python functions. That's well and good,
		but a tad repetitious and annoyingly verbose. Also, there's to be
		a means to grab template definitions out of separate storage...

		In that light, templates have a defined sub-assembly mechanism.
		For example:
		
		page=Template("...{title}...{.body}...{foobar}...")
		user_page = page.assembly(
			 title="Hello, {user}",
			body="...Hello, {user}...{.body}...",
		)
		
		Then user_page acts like a template which takes parameters "user",
		"body", and "foobar". You can bind strings (which become templates),
		or anything that acts like a template. Sub-assemblies may be further
		extended in the same manner without limit.
		"""
		return SubAssembly(self, kwargs)
	

class Template(AbstractTemplate):
	"""
	Any half-decent web framework needs to provide a cooperative templating system.
	This simple but effective approach cooperates with the iolist idea -- at least somewhat.
	
	Create a "Template" object from a string with {keyword} placeholders like this.
	For now, they should be strictly like identifiers. The object is then callable
	with said keyword parameters, and will put everything in the right places.
	Parameters will be entity-encoded unless they begin with a dot like {.this},
	in which case they're passed through as-is. Alternatively, like {this:how} means
	look up ':how' in the registry as a pre-processing step before html-encoding.
	(These are mutually exclusive.)
	"""
	PATTERN = re.compile(r'{(\.?)([_a-zA-Z]\w*)(:\w+)?}')
	REGISTRY = {
		':num': lambda n:'{:,}'.format(n), # Show numbers with thousands-separator.
		':cents': lambda n:'{:,.2f}'.format(n), # That, and also two decimal places.
	}
	
	def __init__(self, text:str):
		self.items = []
		left = 0
		def literal(b:bytes): return lambda x:b
		def escape(keyword:str):
			def fn(x):
				try: item = x[keyword]
				except KeyError: item = '{'+keyword+'}'
				if isinstance(item, str): item = html.escape(item)
				return '' if item is None else item
			return fn
		def preprocess(keyword:str, fn): return lambda x:html.escape(fn(x[keyword]))
		for match in Template.PATTERN.finditer(text):
			if left < match.start(): self.items.append(literal(bytes(text[left:match.start()], 'UTF-8')))
			if match.group(1): self.items.append(operator.itemgetter(match.group(2)))
			elif match.group(3): self.items.append(preprocess(match.group(2), Template.REGISTRY[match.group(3)]))
			else: self.items.append(escape(match.group(2)))
			left = match.end()
		if left < len(text): self.items.append(literal(bytes(text[left:], 'UTF-8')))
	
	def sub(self, parameters):
		return [item(parameters) for item in self.items]

class SubAssembly(AbstractTemplate):
	"""
	This supplies an implementation for snapping templates together to form
	larger templates. Normally you won't use this directly, but will instead
	use the "assembly" method on the base template.
	"""
	def __init__(self, base:AbstractTemplate, bindings:dict):
		self.base = base
		self.bindings = {
			key: Template(value) if isinstance(value, str) else value
			for key, value in bindings.items()
		}
	
	def sub(self, parameters:Mapping):
		parts = {key:binding.sub(parameters) for key, binding in self.bindings.items()}
		return self.base.sub(dict(parameters, **parts))
	

class TemplateLoop:
	"""
	Like 99 times out of 100, you want to present a list of something, and
	that list requires a sensible preamble and epilogue. Oh, and if the list
	happens to be empty, then often as not you want to show something
	completely different. It's such a consistent motif that it almost
	deserves its own control structure.
	
	This is that structure. The object constructor takes templates (or makes
	them from strings) and then the .loop(...) method expects to be called
	with an iterable for repetitions of the loop body. However, if the
	iterable yields no results, you get the `otherwise` template expanded.
	"""
	def __init__(self, preamble, body, epilogue, otherwise=None):
		def coerce(x):
			if isinstance(x, str): return Template(x)
			if callable(x): return x
			assert False, type(x)
		self.preamble = coerce(preamble)
		self.body = coerce(body)
		self.epilogue = coerce(epilogue)
		self.otherwise = otherwise and coerce(otherwise)
	
	def loop(self, items:Iterable[Mapping], context:Mapping=None):
		if context is None:
			context = {}
			sub = self.body.sub
		else:
			def sub(m):
				local = dict(context)
				local.update(m)
				return self.body.sub(local)
		each = iter(items)
		try: first = next(each)
		except StopIteration:
			if self.otherwise: return self.otherwise.sub(context)
			else: return ()
		else: return [
			self.preamble.sub(context),
			sub(first),
			*map(sub, each),
			self.epilogue.sub(context),
		]
	

class TemplateFolder:
	"""
	It's not long before you realize that templates exist to be separated
	from "code". They are OK as here-documents in very small quantities,
	but as soon as you get to developing in earnest, you'll want to see
	them as separate files for at least two reasons: First, you generally
	get much better "smart editor" support. Second, you don't always have
	to restart the service to see changes if you use the provided cache
	management wrapper.
	
	This object provides a means to get templates on-demand from the
	filesystem and keep them around, pre-parsed, for as long as you like.
	For completeness, we also provide a means to means to read a SubAssembly
	straight from a single template file without confusing your editor.
	
	The object provides a service wrapper designed to manage the cache.
	It's appropriate in a single-user scenario. (In a big production web
	server, you normally don't invalidate templates until restart anyway.)
	"""
	
	BEGIN_ASSY = '<extend>'
	END_ASSY = '</extend>'
	
	BEGIN_LOOP = '<loop>'
	END_LOOP = '</loop>'
	
	def __init__(self, path, extension='.tpl'):
		self.folder = pathlib.Path(path)
		assert self.folder.is_dir(), path
		self.extension = extension or ''
		self.__store = {}
	
	def __call__(self, filename:str):
		"""
		:param filename: the basename of a template in the folder.
		:return: the parsed template, ready to go, and cached for next time.
		"""
		try: return self.__store[filename]
		except KeyError:
			with open(self.folder/(filename+self.extension)) as fh:
				text = fh.read().lstrip()
			if text.startswith(self.BEGIN_ASSY): it = self.__read_assembly(text)
			elif text.startswith(self.BEGIN_LOOP): it = self.__read_loop(text)
			else: it = Template(text)
			self.__store[filename] = it
			return it
	
	def __read_assembly(self, text:str) -> SubAssembly:
		"""
		Expect an extension template and turn it into a SubAssembly object.
		It is expected to be a single <extends> tag (case sensitive) with
		possible trailing whitespace. Inside that tag, the first section is
		the name of the base template. The sections after <?name?>
		processing instructions are bindings to the given name. This format
		is chosen not to confuse PyCharm's HTML editor (much).
		"""
		
		bind = self.__read_composite_template(text, len(self.BEGIN_ASSY), self.END_ASSY)
		base = self(bind.pop(None).strip())
		return base.assembly(**bind)
		
	def __read_loop(self, text:str) -> TemplateLoop:
		bind = self.__read_composite_template(text, len(self.BEGIN_LOOP), self.END_LOOP)
		if not bind.keys() <= {None, 'begin', 'end', 'else'}: raise ValueError('Template loop has weird sections.')
		return TemplateLoop(bind[None], bind['begin'], bind.get('end', ''), bind.get('else'))
	
	def __read_composite_template(self, text:str, start:int, end_marker:str) -> dict:
		"""
		Turns out this is a thing...
		I'm defining "composite template" by absurd misuse of XML processing
		instructions... although strictly-speaking, XML-PI are application-
		defined, so I guess there's no such thing as misuse. Anyway, the
		concept is to divide the input text wherever an XML-PI occurs, thus
		producing a dictionary of components. The first component (before any
		division) is keyed to `None`, and everything else is keyed to the name
		of the XML-PI that precedes it.
		"""
		bind = {}
		key = None
		left = start
		try: right = text.rindex(end_marker)
		except ValueError: right=len(text)
		suffix = text[right+len(self.END_ASSY):]
		assert suffix=='' or suffix.isspace()
		for match in re.finditer(r'<\?(.*?)\?>', text):
			bind[key] = text[left:match.start()].strip()
			key = match.group(1).strip()
			left = match.end()
		bind[key] = text[left:right].strip()
		return bind

	
	def wrap(self, handler):
		"""
		This wraps a handler in a function that invalidates the template cache on
		every hit. That's useful in development while you're tweaking templates, but
		you might turn it off for production use. You'll typically use this as:
		
		tpl = TemplateFolder('templates')
		app = Router()
		.... various set-up and defining your application ...
		serve_http(tpl.wrap(app))
		"""
		def wrapper(request:Request)->Response:
			self.__store.clear()
			return handler(request)
		return wrapper


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
	
	TEMPLATE_GENERIC = Template("""
	<!DOCTYPE html>
	<html><head><title>{title}</title></head>
	<body> <h1>{title}</h1>
	{.body}
	<hr/>
	<pre style="background:black;color:green;padding:20px;font-size:15px">Python Version: {python_version}\r\nKali version {kali_version}</pre>
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
			if node.entry is not None and i > best: found, best = node, i
			if i<len(path) and self.WILDCARD in node.kids: backtrack.append((node.kids[self.WILDCARD], i + 1))
			if i<len(path) and path[i] in node.kids: node, i = node.kids[path[i]], i + 1
			elif backtrack: node, i = backtrack.pop()
			elif found is None: return Response.generic(code=404)
			else:
				request.mount_depth = best
				handler, wildcards = found.entry
				request.args = [path[i] for i in wildcards]
				return handler(request)
	
	def delegate(self, where:str, handler:Callable[[Request], Response]):
		"""
		This is the most-general way to attach functionality to an URL-path,
		potentially with wildcards. This is where to document how virtual path
		specifiers work.
		
		The empty string means the absolute root folder, not its index.
		Any other string must begin with a slash. Leading slashes are removed,
		and then the string is broken into path components.
		"""
		node, wildcards = self.root, []
		if where != '':
			assert where.startswith('/'), "Non-root mount points begin with a slash."
			path = where.lstrip('/').split('/')
			assert all(path[:-1]), "Please do not embed blank components in your virtual paths."
			for index, item in enumerate(path):
				assert not item.startswith('.'), "Path components beginning with dots are reserved."
				if item == self.WILDCARD: wildcards.append(index)
				node = node.dig(item)
		assert node.entry is None, "You've previously mounted something at this same path."
		node.entry = (handler, tuple(wildcards))
	
	def delegate_folder(self, where:str, handler:Callable[[Request], Response]):
		"""
		Say you've a handler that expects to be a folder. Then there is certain
		shim code in common. This provides that shim.
		"""
		assert where.endswith('/'), "Services mount at a folder, not a file. (End virtual-path with a slash.)"
		def shim(request:Request) -> Response:
			if request.has_suffix(): return handler(request)
			else: return Response.redirect(request.app_url([''], request.GET))
		self.delegate(where[:-1], shim)

	def function(self, where:str):
		"""
		Apply this parameterized decorator to publish functions.
		Use wildcards in the path to indicate positional arguments.
		Query arguments get translated to keyword parameters.
		A function will respond to GET requests, but anything else results
		in 501 Not Implemented. To support POST you'll need to write a class
		and decorate it with either @servlet('...') or @service('...').
		"""
		def decorate(fn):
			def proxy(request:Request):
				if request.command == 'GET' and not request.has_suffix():
					return fn(*request.args, **request.GET.single)
				else:
					return Response.generic(501)
			self.delegate(where or '/', proxy)
			if where.endswith('/') and where != '/':
				self.delegate_folder(where, lambda x:Response.generic(code=404))
			return fn
		return decorate
	
	def servlet(self, where, allow_suffix=False):
		"""
		Wildcards in the path become positional arguments to the constructor
		for the class this expects to decorate. Then a do_GET or do_POST
		method gets called with the actual `Request` object as a parameter.
		"""
		def decorate(cls):
			assert isinstance(cls, type), type(cls)
			def servlet_handler(request:Request):
				if (not request.has_suffix()) or allow_suffix:
					instance = cls(*request.args)
					method = getattr(instance, 'do_' + request.command, None)
					if method is not None:
						return method(request)
				return Response.generic(501)
			self.delegate(where, servlet_handler)
			return cls
		return decorate
	
	def service(self, where:str):
		"""
		Similar to servlet, but one major difference: This expects
		to service an entire (virtual) folder using instance methods
		named like do_GET_this or do_POST_that.
		"""
		assert where.endswith('/'), "Services mount at a folder, not a file. (End virtual-path with a slash.)"
		def decorate(cls):
			assert isinstance(cls, type), type(cls)
			def service_handler(request:Request):
				suffix = request.path_suffix()
				if len(suffix) == 1:
					instance = cls(*request.args)
					name = suffix[0]
					method = getattr(instance, 'do_' + request.command+"_"+name, None)
					if method: return method(request)
				return Response.generic(code=501)
			self.delegate_folder(where, service_handler)
		return decorate



class RouteNode:
	""" Just a simple tree node. Nothing to see here. Move along. """
	def __init__(self):
		self.entry, self.kids = None, {}
	def dig(self, label):
		try: return self.kids[label]
		except KeyError:
			self.kids[label] = it = RouteNode()
			return it

class StaticFolder:
	"""
	A simple handler to present the contents of a filesystem folder
	to the browser over HTTP. It forbids path components that begin
	with a dot or underscore as a simple safety measure. Attach it
	to your router via `delegate_folder`.
	"""
	
	LINK = Template("""<li><a href="{name}">{name}</a></li>\r\n""")
	
	@staticmethod
	def forbid(component):
		return component[0] in '._'
	
	def __init__(self, real_path):
		self.root = real_path
	
	def __call__(self, request:Request):
		suffix = request.path_suffix()
		want_folder = suffix[-1] == ''
		if want_folder: suffix.pop()
		if any(map(StaticFolder.forbid, suffix)): return Response.generic(code=403)
		local_path = os.path.join(self.root, *  suffix)
		try:
			if want_folder:
				up = StaticFolder.LINK(name='..') if len(request.path) > 1 else b''
				body = [
					StaticFolder.LINK(name=fn+['', '/'][os.path.isdir(os.path.join(local_path,fn))])
					for fn in os.listdir(local_path)
					if not StaticFolder.forbid(fn)
				]
				return Response.generic(
					['<ul>', up, body, '</ul>'],
					title='Showing Folder /'+'/'.join(request.path[:-1]),
				)
			else:
				with open(local_path, 'rb') as fh:
					return Response.plain_text(fh.read())
		except OSError:
			return Response.generic(code=404)
	
class Servlet:
	"""
	This class does absolutely nothing of consequence, but if you derive a
	subclass from it then your IDE will probably be able to fill in method
	prototypes for the derived subclass.
	"""
	def do_GET(self, request:Request) -> Response:
		raise NotImplementedError(type(self))
	
	def do_POST(self, request:Request) -> Response:
		raise NotImplementedError(type(self))
