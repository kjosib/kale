"""
There's always a layer of goo that isn't really specific to the task at hand,
but isn't quite generic enough to have a good home in the standard library.

This is that layer -- at least, for now.
"""

__all__ = ['Bag', ]

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

