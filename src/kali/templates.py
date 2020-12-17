

__all__ = [ 'Template', 'TemplateFolder', ]

import re, html, operator, pathlib
from typing import Mapping, Iterable

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

	def invalidate_cache(self):
		"""
		This is beginning to suggest a violation of single-responsibility principle.
		"""
		self.__store.clear()

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
		def wrapper(request:"Request")->"Response":
			self.invalidate_cache()
			return handler(request)
		return wrapper
