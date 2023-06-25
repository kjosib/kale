"""
Single-threaded web application service framework designed as an alternative to
ordinary desktop application development. See http://github.com/kjosib/kali

HTTP is essentially a request/respond protocol:
The server proceeds by first building a request object (based on whatever the
browser transmits) and then routes the request to a suitable handler, which
constructs a response.

Things can go wrong in several ways:

While reading the request
While constructing a response
While transmitting a response

And, in general, an error response should be able to refer to bits of the request.

"""

__all__ = [
	'serve_http', 'Router', 'StaticFolder', 'Servlet',
]

import socket, urllib.parse, re, os, logging, math
from typing import Callable, Optional
import traceback
from . import requesting, responding, utility, templates

HTTP_DEFAULT_ENCODING = 'iso8859-1'
HTTP_EOL = b'\r\n'
LEN_HTTP_EOL = len(HTTP_EOL)

MAX_UPLOAD_SIZE = 10_000_000

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
	:param timeout: How long to wait for additional data from a slow browser.
	:return: only if the handler ever sets the `shutdown` flag in a response.
	"""
	log_lines = {
		code: "<--  %d %s"%(code, str(reason, 'UTF-8', errors='replace'))
		for code, reason in responding.Response.REASON.items()
	}
	def reply(response:responding.Response):
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
		try: request = ClientReader(client, timeout=timeout).build_request()
		except socket.timeout: log.info("Timed out.") # No reply; just hang up and move on.
		except ProtocolError as pe:
			log.warning("Protocol Error: %s %s", pe, traceback.format_exc())
			reply(responding.Response.generic(code=400))
		else:
			try:
				response = handle(request)
				if not isinstance(response, responding.Response): response = responding.Response(response)
				alive = not response.shut_down
			except:
				log.exception("During %s %s", request.command, request.uri)
				response = responding.Response.from_exception(request)
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
			if not self.waited: self.collect_more_packets(math.inf)
			try: return self.blob.index(what, self.start)
			except ValueError: raise
	
	def collect_more_packets(self, limit):
		self.waited = True
		block = self.blob[self.start:]
		packets = [block]
		size = len(block)
		while size < limit:
			try: block = self.get_one_packet()
			except socket.timeout: break
			if block:
				packets.append(block)
				size += len(block)
			else: break
			if size > MAX_UPLOAD_SIZE: raise ProtocolError()
		self.blob = b''.join(packets)
		self.start = 0

	def read_bytes_until(self, delimiter:bytes):
		end = self.go_find(delimiter)
		start = self.start
		self.start = end + len(delimiter)
		return self.blob[start:end]

	def read_line_bytes(self) -> bytes:
		try: return self.read_bytes_until(HTTP_EOL)
		except ValueError: raise ProtocolError()

	def unput(self, line:bytes):
		self.start -= len(line)+LEN_HTTP_EOL

	def exhausted(self):
		return self.start == len(self.blob) and self.waited
	
	def expect_rest(self):
		if not self.waited: self.collect_more_packets(math.inf)
		return len(self.blob) - self.start

	def read_headers(self, headers:utility.Bag):
		while not self.exhausted():
			line = self.read_line_bytes()
			log.debug("header: %s", line)
			assert isinstance(line, bytes)
			if not line: return
			if line.startswith(b'--'):
				self.unput(line)
				return
			if b':' in line:
				key, value = str(line, HTTP_DEFAULT_ENCODING).split(': ', 2)
				headers[key.lower()] = value
			else:
				raise ProtocolError('Bogus Line: %r' % line)

	def peek(self, size) -> bytes:
		return self.blob[self.start:self.start+size]

	def build_request(self) -> requesting.Request:

		def multipart_mode(delimiter:bytes):
			"""
			See https://tools.ietf.org/html/rfc7578 to understand what this is doing.
			And yes it might be simpler to exploit a MIME library.
			The RFC is what I actually found when looking into this.
			:yield: pairs of key/value, where the values may be file uploads.
			"""
			while not self.exhausted():
				try: part = self.read_bytes_until(delimiter)
				except ValueError:
					log.debug("trailer: %r", self.peek(100))
					return
				if len(part)>10:
					analyze_single_part(post, part[:-LEN_HTTP_EOL])

		def bogus_payload():
			log.warning("content-type was %s", headers.get('content-type'))
			log.warning("Command: %s %s %s", command, uri, protocol)
			log.warning("Payload: %r", self.peek(min(content_length, 256)))

		command, uri, protocol = str(self.read_line_bytes(), HTTP_DEFAULT_ENCODING).split()
		log.info(' -> %s %s', command, uri)
		headers = utility.Bag()
		post = utility.Bag()
		self.read_headers(headers)
		if 'content-length' in headers:
			content_length = int(headers['content-length'])
			self.collect_more_packets(content_length)
		else:
			content_length = self.expect_rest()
		# At this point, there are two possibilities:
		content_type = headers.get('content-type')
		if content_type is None:
			if self.peek(2) == b'--': multipart_mode(self.read_line_bytes())
			elif content_length: bogus_payload()
		elif content_type == 'application/x-www-form-urlencoded':
			post.update(urllib.parse.parse_qsl(str(self.peek(content_length), 'UTF-8'), keep_blank_values=True))
		elif content_type.startswith("multipart/form-data;"):
			try: boundary_parameter = bytes(content_type.split('boundary=')[1], HTTP_DEFAULT_ENCODING)
			except: raise ProtocolError()
			multipart_mode(b'--' + boundary_parameter)
		elif content_length: bogus_payload()
		return requesting.Request(command, uri, protocol, headers, post)


def analyze_single_part(post: utility.Bag, part:bytes):
	"""
	Here we have a similar problem to the original ClientReader, but now it's
	line-at-a-time.
	"""
	try: head, body = part.split(HTTP_EOL+HTTP_EOL, 1)
	except ValueError:
		log.warning("Broken Part (length=%s) %s", len(part), part[:100])
		return
	name, filename, content_type = None, None, 'text/plain'
	for line in head.split(HTTP_EOL):
		if not line: continue
		k,v = str(line, HTTP_DEFAULT_ENCODING).split(': ', 1)
		if k == 'Content-Disposition': name, filename = analyze_disposition(v)
		elif k == 'Content-Type': content_type = v
		else: raise ProtocolError(k)
	if filename is None: post[name] = str(body, HTTP_DEFAULT_ENCODING)
	else: post[name] = requesting.FileUpload(filename, content_type, body)

def analyze_disposition(disposition:str):
	m = re.fullmatch(r'form-data; name="([^"]*)"; filename="([^"]*)"', disposition)
	if m: return m.groups()
	m = re.fullmatch(r'form-data; name="([^"]*)"', disposition)
	if m: return m.group(1), None
	log.warning("Odd Content-Disposition: %s", disposition)
	raise ProtocolError()

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
	
	def __call__(self, request: requesting.Request):
		""" Route a request to the appropriate handler based on the deepest/longest match to a mount point. """
		normalize = request.normalize()
		if normalize is not None: return responding.Response.redirect(normalize)
		
		# OK, that test passed. Now go find the most applicable handler.
		# A not-too-complicated back-tracking search. I anticipate that
		# real applications won't stress this too hard.
		path, node, i, found, best, backtrack = request.path, self.root, 0, None, -1, []
		while True:
			if node.entry is not None and i > best: found, best = node, i
			if i<len(path) and self.WILDCARD in node.kids: backtrack.append((node.kids[self.WILDCARD], i + 1))
			if i<len(path) and path[i] in node.kids: node, i = node.kids[path[i]], i + 1
			elif backtrack: node, i = backtrack.pop()
			elif found is None: return responding.Response.generic(code=404)
			else:
				request.mount_depth = best
				handler, wildcards = found.entry
				request.args = [path[i] for i in wildcards]
				return handler(request)
	
	def delegate(self, where:str, handler:Callable[[requesting.Request], responding.Response]):
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
	
	def delegate_folder(self, where:str, handler:Callable[[requesting.Request], responding.Response]):
		"""
		Say you've a handler that expects to be a folder. Then there is certain
		shim code in common. This provides that shim.
		"""
		assert where.endswith('/'), "Services mount at a folder, not a file. (End virtual-path with a slash.)"
		def shim(request:requesting.Request) -> responding.Response:
			if request.has_suffix(): return handler(request)
			else: return responding.Response.redirect(request.app_url([''], request.GET))
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
			def proxy(request:requesting.Request):
				if request.command == 'GET' and not request.has_suffix():
					return fn(*request.args, **request.GET.single)
				else:
					return responding.Response.generic(501)
			self.delegate(where or '/', proxy)
			if where.endswith('/') and where != '/':
				self.delegate_folder(where, lambda x:responding.Response.generic(code=404))
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
			def servlet_handler(request:requesting.Request):
				if (not request.has_suffix()) or allow_suffix:
					instance = cls(*request.args)
					method = getattr(instance, 'do_' + request.command, None)
					if method is not None:
						return method(request)
				return responding.Response.generic(501)
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
			def service_handler(request:requesting.Request):
				suffix = request.path_suffix()
				if len(suffix) == 1:
					instance = cls(*request.args)
					name = suffix[0]
					method = getattr(instance, 'do_' + request.command+"_"+name, None)
					if method: return method(request)
				return responding.Response.generic(code=501)
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
	
	LINK = templates.Template("""<li><a href="{name}">{name}</a></li>\r\n""")
	
	@staticmethod
	def forbid(component):
		return component[0] in '._'
	
	def __init__(self, real_path):
		self.root = real_path
	
	def __call__(self, request:requesting.Request):
		suffix = request.path_suffix()
		want_folder = suffix[-1] == ''
		if want_folder: suffix.pop()
		if any(map(StaticFolder.forbid, suffix)): return responding.Response.generic(code=403)
		local_path = os.path.join(self.root, *  suffix)
		try:
			if want_folder:
				up = StaticFolder.LINK(name='..') if len(request.path) > 1 else b''
				body = [
					StaticFolder.LINK(name=fn+['', '/'][os.path.isdir(os.path.join(local_path,fn))])
					for fn in os.listdir(local_path)
					if not StaticFolder.forbid(fn)
				]
				return responding.Response.generic(
					['<ul>', up, body, '</ul>'],
					title='Showing Folder /'+'/'.join(request.path[:-1]),
				)
			else:
				with open(local_path, 'rb') as fh:
					return responding.Response.plain_text(fh.read())
		except OSError:
			return responding.Response.generic(code=404)
	
class Servlet:
	"""
	This class does absolutely nothing of consequence, but if you derive a
	subclass from it then your IDE will probably be able to fill in method
	prototypes for the derived subclass.
	"""
	def do_GET(self, request:requesting.Request) -> responding.Response:
		raise NotImplementedError(type(self))
	
	def do_POST(self, request:requesting.Request) -> responding.Response:
		raise NotImplementedError(type(self))
