"""
If you're choosing to present your application via the browser, chances are
excellent that you'll want to handle POST-forms. It's possible atop the basic
implementation, but this module should make your life easier in this regard.

The concept of operations is that you subclass Formlet and fill in a few
blanks to get fully-working form pages. In practice you'll probably make a
general subclass that talks to your main presentation templates, and then
specific subclasses for each sort of record you want to edit or create.

The base Formlet constructor requires a dictionary of FormElement objects
which give personality to each of the (notional) fields for whatever sort of
record your formlet is editing. The FormElement doesn't store the field name,
so you can reuse the same one for different fields that have basically the
same behavior.

A small note: Dealing gracefully with incomplete or incorrect user-input
is always more challenging than the happy path.
"""

__all__ = [
	'ValidationError', 'SaveError', 'Formlet', 'FormElement',
	'Entry', 'Memo', 'Pick', 'tag', 'Lens', 'StringLens',
	'ChoiceLens', 'EnumLens'
]

import html
from typing import Dict, Iterable, Tuple, Sequence, TypeVar, Mapping
from . import implementation

NATIVE = TypeVar('NATIVE')

class Lens:
	"""
	Not everything is all strings. But in HTML, strings are all there is.
	Not everything is valid. But there are a thousand ways to decide.
	And not every kind of web data entry widget should have to support
	a gazillion options for every conceivable pre/post-processing and
	validation situation.
	
	Instead, they accept an object called a "Lens".
	"""
	def string_for_browser(self, n:NATIVE) -> str:
		""" Convert a native Python value to a string for the web. """
		raise NotImplementedError(type(self))
	
	def native_from_string(self, s:str) -> NATIVE:
		"""
		Convert a string (as from the browser) back to a native
		value for use in the application. THIS MAY FAIL for several
		reasons: Maybe it doesn't parse as a number. Maybe it fails a
		regular expression check. Maybe it's February 30th (nonsense).
		At any rate, if something is wrong, raise ValidationError with an
		appropriate message.
		"""
		raise NotImplementedError(type(self))
	

class StringLens(Lens):
	""" Simple bits for usual stringy cases: """
	def __init__(self, *, error='', blank:str=None):
		self.__error = error
		self.__blank = blank
	
	def string_for_browser(self, n: NATIVE) -> str:
		return '' if n is None else str(n)
	
	def native_from_string(self, s: str) -> NATIVE:
		n = s.strip()
		if n == '':
			if self.__error: raise ValidationError(self.__error)
			else: return self.__blank
		else: return n
	
TYPICAL = StringLens(error='may not be blank.')
NULLABLE = StringLens()
BLANKABLE = StringLens(blank='')

class ChoiceLens(Lens):
	"""
	When the domain of a field ranges over a small finite set of values,
	you typically have a terse internal value and a verbose human-readable
	label for each item. To the methods of `class Lens`, let's add a method
	to iterate over (string-typed, browser-facing) value-label pairs, and to
	get a label corresponding to a value.
	"""
	
	def string_pairs(self):
		raise NotImplementedError(type(self))
	
	def label_for(self, n:NATIVE) -> str:
		raise NotImplementedError(type(self))

class ValidationError(Exception):
	""" Raise with a sensible message about a specific field failing validation. """
	
class SaveError(Exception):
	""" Raise with an errors dictionary. Your display method must cope with it. """

def tag(kind, attributes:dict, content):
	""" Make an HTML tag IoList. Attributes valued `None` are mentioned but not assigned. """
	def assign(key, value):
		if value is None: return [' ', html.escape(key)]
		else: return [' ', html.escape(key), '="', html.escape(value), '"']
	a_text = [assign(*pair) for pair in attributes.items()]
	if content is None: return ["<",kind,a_text,"/>"]
	else: return ["<",kind,a_text,'>',content,"</",kind,">"]

class Formlet:
	"""
	Lots of application forms exist to create or update simple records.
	This class should provide a comfortable functional basis for building
	such form pages quickly and easily. Pass an appropriate dictionary of
	form elements into the constructor (from yours; you'll override it)
	and implement certain abstract methods. Mount the subclass as a servlet
	somewhere, and your typical form interaction is taken care of.

	At any rate, the first thing the GET or POST methods do is save the
	request into self.request, so it's there if you need it during any of
	your overrides EXCEPT YOUR CONSTRUCTOR.

	What's a form element? Read on.
	"""
	
	def __init__(self, elements: Dict[str, "FormElement"]):
		self.elements = elements
		self.request = None
	
	def get_native(self) -> dict:
		"""
		Return a dictionary representing the native information the form
		starts out with. Perhaps you query a database for a current record,
		or perhaps you provide a blank record for a "create" screen.
		"""
		raise NotImplementedError(type(self))
	
	def display(self, fields:dict, errors:dict) -> implementation.Response:
		"""
		Display a form, with the HTML bits corresponding to the fields,
		and potentially with any errors from a failed attempt. Field-specific
		errors will be in corresponding keys of the errors dictionary.
		Other kinds of errors are whatever you do in the semantic_checks
		method and/or toss as an argument to a SaveError.
		"""
		raise NotImplementedError(type(self))
	
	def semantic_checks(self, native:dict, errors:dict):
		"""
		Perform any formlet-specific semantic checks beyond what the
		form elements can do on their own. For example, check that a
		start-date precedes an end-dat.
		
		If anything goes wrong, set one or more entries in the errors
		dictionary. Don't forget it's your `display` method which receives
		this errors dictionary, so do whatever is meaningful to you.
		
		The default is to do nothing, because in many cases element-
		specific checks are plenty.
		"""
		pass
	
	def save(self, native:dict, request:implementation.Request) -> implementation.Response:
		"""
		Attempt to save the validated results of your form POSTing.
		If anything goes wrong, raise SaveError with an errors dictionary.
		Otherwise, return a response. Typical is to redirect the browser
		back to whatever was before the initial GET action.
		"""
		raise NotImplementedError(type(self))
	
	def do_GET(self, request:implementation.Request) -> implementation.Response:
		def get(key): # Do this to support both incomplete mappings and sqlite Row objects
			try: return native[key]
			except KeyError: return None
		self.request = request
		native = self.get_native()
		intermediate = {key: elt.n2i(get(key)) for key, elt in self.elements.items()}
		return self._display(intermediate, {})
	
	def _display(self, intermediate:dict, errors:dict) -> implementation.Response:
		fields = {key: elt.i2h(key, intermediate[key]) for key, elt in self.elements.items()}
		return self.display(fields, errors)
	
	def do_POST(self, request:implementation.Request) -> implementation.Response:
		self.request = request
		intermediate = {}
		native = {}
		errors = {}
		for key, elt in self.elements.items():
			i = intermediate[key] = elt.p2i(key, request.POST)
			try: native[key] = elt.i2n(i)
			except ValidationError as ve: errors[key] = ve.args[0]
		if not errors: self.semantic_checks(native, errors) # which may add to errors.
		if errors: return self._display(intermediate, errors)
		try: return self.save(native, request)
		except SaveError as se:
			errors = se.args[0]
			assert isinstance(errors, dict) and errors, type(errors)
			return self._display(intermediate, errors)
		

class FormElement:
	"""
	In the abstract, a FormElement is a two-step mapping between native data,
	some intermediate form, and the browser's HTML->POST data cycle. Thus,
	it has four methods. With a bit of care, you can build lenses that
	groom and validate the data where and when appropriate.
	
	In a spirit of excessive abbreviation, the abstract methods are named
	x2y, where x and y are drawn from:
		n: native Python data (for your application)
		i: intermediate form, able to round-trip bad entries with the browser
		h: HTML
		p: POST data
	"""
	
	def n2i(self, value):
		""" Return intermediate data corresponding to given native value. """
		raise NotImplementedError(type(self))
	
	def p2i(self, name:str, POST:implementation.Bag):
		"""
		Return intermediate data coming in from POST. This should not fail
		(so long as the browser plays nice) and it must be possible to
		recreate whatever the end-user entered even if it doesn't make sense
		to the application. In the unlikely event of a problem, raise an
		ordinary exception so the programmer realizes the mistake.
		"""
		raise NotImplementedError(type(self))
	
	def i2h(self, name, intermediate):
		"""
		Return an HTML IoList corresponding to an intermediate value. This
		may get complex, as in drop-down selections or date entry fields.
		"""
		raise NotImplementedError(type(self))
	
	def i2n(self, intermediate) -> object:
		"""
		Convert an intermediate value (as known to the FormElement) back to
		native form for use in the application. Normally delegates to a Lens.
		"""
		raise NotImplementedError(type(self))

class Entry(FormElement):
	""" A typical single-line form input box taking enough parameters to be usually useful. """
	def __init__(self, *, lens:Lens=TYPICAL, **kwargs):
		""" **kwargs become tag attributes. Use _class to set the CSS class. maxlength is enforced. """
		self.maxlength = int(kwargs.get('maxlength', 0))
		self.lens = lens
		self.attributes = {k:str(v).lstrip('_') for k,v in kwargs.items()}

	def n2i(self, value): return self.lens.string_for_browser(value)
	
	def p2i(self, name: str, POST: implementation.Bag):
		intermediate = POST.get(name, '')
		if self.maxlength and len(intermediate) > self.maxlength:
			intermediate = intermediate[:self.maxlength]
		return intermediate
	
	def i2h(self, name, intermediate):
		return tag('input', {'type': 'text', **self.attributes, 'name': name, 'value': intermediate, }, None)
	
	def i2n(self, intermediate) -> object:
		return self.lens.native_from_string(intermediate)

class Memo(Entry):
	""" A textarea. This differs from an entry field only in the i2h method. """
	def i2h(self, name, intermediate):
		return tag('textarea', {**self.attributes, 'type': 'text', 'name': name}, html.escape(intermediate))


def option(value: str, label: str, selected: bool):
	""" Pick lists of all sorts need a simple way to get the entries made. """
	first = '<option selected value="' if selected else '<option value="'
	return [first, html.escape(value), '">', html.escape(label), '</option>']


class Pick(FormElement):
	"""
	A selection box. Handles single and multiple selection.
	Expects a `ChoiceLens` object following the 'strategy' pattern.
	"""
	def __init__(self, lens:ChoiceLens, required:str='', multiple:bool=False, **kwargs:dict):
		"""
		Create a selection box.
		:param lens: works in the usual manner; on each element of a set if a multi-selection.
		:param required: If non-blank, the error message to raise on empty input.
		:param multiple: Allow and support multiple-selection.
		:param kwargs: Other attributes to the <select...> tag.
		"""
		assert "multiple" not in map(str.lower, kwargs.keys())
		self.lens = lens
		self.required = required
		self.multiple = multiple
		self.attributes = {k:str(v).lstrip('_') for k,v in kwargs.items()}
		if multiple: self.attributes['multiple'] = ''
	
	def option_tags(self, intermediate) -> Iterable[Tuple[str, str, bool]]:
		""" Work in terms of the intermediate value to support weird cases. """
		if self.multiple:
			test = intermediate.__contains__
		else:
			test = intermediate.__eq__
			if not (self.required and intermediate):
				yield '', '', False
		for value, label in self.lens.string_pairs():
			assert isinstance(value, str), type(value)
			assert isinstance(label, str), type(label)
			yield value, label, test(value)
	
	def value_label_pairs(self) -> Iterable[Tuple[str, str]]:
		""" This needs to work at the level of browser-facing strings. """
		raise NotImplementedError(type(self))
	
	def i2h(self, name, intermediate):
		opt_html = [option(*o) for o in self.option_tags(intermediate)]
		return tag('select', {**self.attributes, 'name':name}, opt_html)
	
	def n2i(self, value):
		if self.multiple: return set(map(self.lens.string_for_browser, value))
		else: return self.lens.string_for_browser(value)
	
	def p2i(self, name: str, POST: implementation.Bag):
		if self.multiple: return POST.get_list(name)
		else: return POST[name]
	
	def i2n(self, intermediate) -> object:
		if self.required and not intermediate: raise ValidationError(self.required)
		if self.multiple: native = set(map(self.lens.native_from_string, intermediate))
		else: native = self.lens.native_from_string(intermediate)
		return native
	
class EnumLens(ChoiceLens):
	"""
	Specialized to select the (integer) offset into a short constant list of
	values which you provide to this object's constructor.
	"""
	def __init__(self, options:Sequence, *, base=0, reverse=False):
		"""
		:param options: The sequence of valid options, provided up front.
		:param base: The least number in your enumeration.
		:param reverse: If true, offer options back-to-front.
		"""
		self.options = options
		self.base = base
		self.__pairs = [
			(str(index), str(label))
			for index, label in enumerate(options)
		]
		if reverse: self.__pairs.reverse()
	
	def string_pairs(self): yield from self.__pairs
	
	def label_for(self, n: int) -> str:
		return '' if n is None else str(self.options[n - self.base])
	
	def string_for_browser(self, n: NATIVE) -> str:
		return '' if n is None else str(n-self.base)
	
	def native_from_string(self, s: str) -> NATIVE:
		if not s: return None
		offset = int(s)
		if 0 <= offset < len(self.options): return offset + self.base
		else: raise ValidationError('out of range (How did you do that?)')
	
