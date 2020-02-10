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
"""

__all__ = [
	'Formlet', 'FormElement', 'ValidationError', 'SaveError', 'Entry', 'tag',
]

import html
from typing import List, Dict, Iterable, Callable, Optional
from . import implementation


class ValidationError(Exception):
	""" Raise with a sensible message about a specific field failing validation. """
	
class SaveError(Exception):
	""" Raise with an errors dictionary. Your display method must cope with it. """

def tag(kind, attributes:dict, content):
	""" Make an HTML tag IoList."""
	a_text = [' %s="%s"'%(html.escape(key), html.escape(value)) for key,value in attributes.items()]
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
	
	def display(self, html:dict, errors:dict) -> implementation.Response:
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
		start-date precedes an end-date. If anything goes wrong, set
		a key-value pair in the errors dictionary. Don't forget it's
		your display method which gets PASSED this errors dictionary,
		so do whatever is meaningful to you.
		
		:return nothing.
		"""
		raise NotImplementedError(type(self))
	
	def save(self, native:dict, request:implementation.Request) -> implementation.Response:
		"""
		Attempt to save the validated results of your form POSTing.
		If anything goes wrong, raise SaveError with an errors dictionary.
		Otherwise, return a response. Typical is to redirect the browser
		back to whatever was before the initial GET action.
		"""
		raise NotImplementedError(type(self))
	
	def do_GET(self, request:implementation.Request) -> implementation.Response:
		self.request = request
		return self._display(self._n2i(self.get_native()), {})
	
	def _n2i(self, native:dict) -> dict:
		return {key: elt.n2i(native[key]) for key, elt in self.elements.items()}
	
	def _display(self, intermediate:dict, errors:dict) -> implementation.Response:
		html = {key: elt.i2h(key, intermediate[key]) for key, elt in self.elements.items()}
		return self.display(html, errors)
	
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
	
	def p2i(self, key:str, POST:implementation.Bag):
		"""
		Return intermediate data coming in from POST. This should not fail
		(so long as the browser plays nice) and it must be possible to
		recreate whatever the end-user entered even if it doesn't make sense
		to the application. In the unlikely event of a problem, raise an
		ordinary exception so the programmer realizes the mistake.
		"""
		raise NotImplementedError(type(self))
	
	def i2h(self, key, intermediate):
		"""
		Return an HTML IoList corresponding to an intermediate value. This
		may get complex, as in drop-down selections or date entry fields.
		"""
		raise NotImplementedError(type(self))
	
	def i2n(self, intermediate) -> object:
		"""
		Given an intermediate value (as back from the browser) convert to
		native form for use in the application. THIS MAY FAIL for several
		reasons: Maybe it doesn't parse as a number. Maybe it fails a
		regular expression check. Maybe it's February 30th (nonsense).
		At any rate, if something is wrong, raise ValidationError with an
		appropriate message.
		"""
		raise NotImplementedError(type(self))

class Entry(FormElement):
	""" A typical single-line form input box taking enough parameters to be usually useful. """
	def __init__(self, *, pre=str.strip, valid=lambda s:True, fail:str=None, **kwargs):
		""" **kwargs become tag attributes. Use _class to set the CSS class. maxlength is enforced. """
		self.maxlength = int(kwargs.get('maxlength', 0))
		self.pre=pre
		self.valid=valid
		self.fail=fail
		self.attributes = {k:str(v).lstrip('_') for k,v in kwargs.items()}

	def n2i(self, value):
		return str(value)
	
	def p2i(self, key: str, POST: implementation.Bag):
		intermediate = POST.get(key, '')
		if self.maxlength and len(intermediate) > self.maxlength:
			intermediate = intermediate[:self.maxlength]
		return intermediate
	
	def i2h(self, key, intermediate):
		return tag('input', {**self.attributes, 'type': 'text', 'name': key, 'value': intermediate, }, None)
	
	def i2n(self, intermediate) -> object:
		native = self.pre(intermediate)
		if self.valid(native): return native
		else: raise ValidationError(self.fail)

class Memo(Entry):
	""" A textarea. This differs from an entry field only in the i2h method. """
	def i2h(self, key, intermediate):
		return tag('textarea', {**self.attributes, 'type': 'text', 'name': key}, html.escape(intermediate))

