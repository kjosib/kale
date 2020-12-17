
__all__ = ['Request', 'FileUpload', ]

import urllib.parse
from typing import List, NamedTuple
from . import utility


class FileUpload(NamedTuple):
	filename: str
	content_type: str
	content: bytes


class Request:
	"""
	The "request object" which a responder function can query.
	To promote testability, the constructor accepts native python data.
	The conversion from network binary blob happens in a static method that RETURNS a request.
	"""
	def __init__(self, command, uri, protocol, headers:utility.Bag, post:utility.Bag):
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
		self.GET = utility.Bag(urllib.parse.parse_qsl(self.url.query, keep_blank_values=True))
		self.POST = post

	def normalize(self):
		path, normal = self.path, []
		for e in path:
			if e == '..': normal.pop()
			elif e in ('', '.'): pass
			else: normal.append(e)
		if path[-1] == '': normal.append('')
		if len(normal) < len(path):
			return self.root_url(normal, self.GET or None)

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

