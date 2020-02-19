"""
This example is a toy datebook application: You can use it to keep track of
contacts and appointments. It's meant to proof out the forms sub-library,
but it is (going to be) a reasonably-complete example.

It uses SQLite for data storage. In a complex application you might write
some query wrappers or use some pre-packaged ones so you get better errors.

It also keeps (ephemeral) state across page requests, for things like table
sort order. It's sort of like session data, but since there's only one user
the "session" object is just the global scope.
"""
import sqlite3, pathlib, sys, datetime
from typing import Iterable, Mapping, Dict
from kali import serve_http, Router, Request, Response, TemplateFolder, forms, implementation

# I want to use SQLite, and store my data in your home folder....
connection = sqlite3.connect(
	str(pathlib.Path.home() / 'datebook.sqlite'),
	detect_types=sqlite3.PARSE_DECLTYPES,
)
connection.row_factory = sqlite3.Row
cursor = connection.cursor()
def Q(text:str, params:Iterable=()):
	""" Stuff happens. I like to see what query failed, if it did. """
	try: return cursor.execute(text, params)
	except:
		print("Failing query was:", file=sys.stdout)
		print(text, file=sys.stdout)
		sys.stdout.flush()
		raise
Q('pragma foreign_keys = on') # Don't ask me why it's not the default.

# Also some database convenience bits will be handy:
def comma(xs): return ','.join(xs)
def eqs(keys): return comma(k+'=?' for k in keys)
def insert(table:str, record:Mapping):
	sql = "insert into %s (%s) values (%s)" % (table, comma(record.keys()), comma('?' * len(record)))
	Q(sql, list(record.values()))
def update(table:str, *, assign:Mapping, where:Mapping, ):
	sql = "update %s set %s where %s" % (table, eqs(assign.keys()), eqs(where.keys()))
	Q(sql, [*assign.values(), *where.values()])


# Set up the database if necessary.
with open(pathlib.Path(__file__).parent/"datebook.sql") as fh:
	for query in fh.read().split(';'):
		Q(query)

# Now, let's try to use templates for all this business:
tpl = TemplateFolder(pathlib.Path(__file__).parent/"datebook.tpl")

app = Router()

# You often find yourself wanting some ephemeral application state,
# such as the current sort order for some list.
STATE = {
	'task_order': 'priority',
}

@app.function('/')
def dashboard():
	""" The "home screen" is a preview of current events... """
	# Yes, a one-line function is a good function.
	return tpl('dashboard')(appt = coming_appointments(), task = pending_tasks())

def coming_appointments():
	""" You'll begin to sense a theme of tiny little functions. """
	today = datetime.date.today()
	next_week = today + datetime.timedelta(7)
	Q("""
		select appointment.*, ifnull(name, '') as name
		from appointment left join contact using (contact)
		where date between ? and ?
		order by date
	""", [today, next_week])
	return tpl('appt_list').loop(cursor)

def pending_tasks():
	order = {
		'priority': "priority asc, ifnull(due, '9999-99-99') asc",
		'due': "ifnull(due, '9999-99-99') asc, priority asc",
	}[STATE['task_order']]
	Q("select * from task where not complete order by "+order)
	return tpl('task_list').loop(cursor)

@app.function('/task/sort/*')
def set_task_sort_order(order):
	assert order in ('priority', 'due')
	STATE['task_order'] = order
	return Response.redirect("/")

# An application like this needs some way to enter data.
# Let's start with something for to-do list entries. We'll use the
# forms support library to make a set of form elements and two servlets
# for adding and editing task entries.

PRIORITIES = forms.EnumLens(['High', 'Medium', 'Low'], base=1)
YES_NO = forms.EnumLens(['No', 'Yes',], reverse=True)
TASK_ELEMENTS = {
	'priority': forms.Pick(PRIORITIES, required='Please select a priority.'),
	'complete': forms.Pick(YES_NO, required="So is it complete or not?"),
	'title': forms.Entry(),
	'memo': forms.Memo(lens=forms.BLANKABLE),
	'due': forms.Entry(type='date', lens=forms.DATE),
}

@app.servlet('/task/new')
class NewTask(forms.Formlet):
	def __init__(self):
		super().__init__(TASK_ELEMENTS)
	
	def get_native(self) -> dict:
		return {'complete':0}
	
	def display(self, fields: dict, errors: dict) -> Response:
		return tpl('task_form')(**fields, errors=errors)
	
	def save(self, native: dict, request: Request) -> Response:
		insert('task', native)
		connection.commit()
		return Response.redirect('/')

@app.servlet('/task/*')
class EditTask(forms.Formlet):
	def __init__(self, task_id_string):
		self.task = int(task_id_string)
		super().__init__(TASK_ELEMENTS)
	
	def get_native(self) -> dict:
		Q("select * from task where task = ?", [self.task])
		return next(cursor)
	
	def display(self, fields: dict, errors: dict) -> Response:
		return tpl('task_form')(**fields, errors=errors)
	
	def save(self, native: dict, request: Request) -> Response:
		update('task', assign=native, where={'task':self.task})
		connection.commit()
		return Response.redirect('/')

@app.function('/contact/')
def list_contacts(*, q=''):
	"""
	Let's move on to the contact-list feature.
	This function implements the searchable list of contacts.
	The corresponding template contains a <form method="GET"> element.

	:param q: Recall that the app router passes URL query parameters as
	          keyword arguments. It's a good idea (and often necessary)
	          to supply default values for such arguments.

	:return: in the usual manner for one of these functions...
	"""
	# Building queries dynamically by hand? There's got to be a better way...
	select = " select * from contact "
	order = " order by name "
	if q:
		where = " where name like ? or address like ? or memo like ? "
		Q(select + where + order, ['%'+q+'%']*3)
	else:
		Q(select + order)
	return tpl('contact_home')(q=q, rows=tpl('contact_list').loop(cursor))

@app.servlet('/contact/new')
@app.servlet('/contact/*')
class ContactForm(forms.Formlet):
	"""
	If you think about it, the "Add" and "Edit" functionality is extremely
	similar. The same `Formlet` subclass can handle both cases. It's up to
	you which approach you prefer.
	
	One possible virtue of the combined approach is the (maybe) additional
	cohesion of keeping the set of relevant FormElement objects as a class
	attribute rather than separately.
	"""
	PHONE = forms.Test(r'[-,;0-9()/]*', error='can contain only numbers and ()-,;/ characters.')
	EMAIL = forms.Test(r'|\S*@\S+\.[a-zA-Z]+', error='does not look much like an e-mail address.')
	ELEMENTS = {
		'name': forms.Entry(style='flex:1'),
		'phone': forms.Entry(lens=PHONE, style='flex:1'),
		'email': forms.Entry(lens=EMAIL, style='flex:1'),
		'address': forms.Memo(lens=forms.BLANKABLE, style='width:100%'),
		'memo': forms.Memo(lens=forms.BLANKABLE, style='width:100%'),
	}
	
	def __init__(self, contact_id=None):
		self.contact_id = int(contact_id) if contact_id else None
		super().__init__(self.ELEMENTS)
	
	def get_native(self) -> dict:
		if self.contact_id is None:
			return {}
		else:
			Q("select * from contact where contact=?", [self.contact_id])
			return next(cursor)
	
	def display(self, fields: dict, errors: dict) -> implementation.Response:
		return tpl('contact_form')(errors=errors, **fields)
	
	def save(self, native: dict, request: implementation.Request) -> implementation.Response:
		with connection:
			if self.contact_id is None:
				insert('contact', native)
			else:
				update('contact', where={'contact':self.contact_id}, assign=native)
		return Response.redirect('/contact/')


@app.servlet('/appt/new')
@app.servlet('/appt/*')
class AppointmentForm(forms.Formlet):
	"""
	At this point, things start to seem a bit -- monotonous?
	Subclass `Formlet`; configure a few virtual methods; draw up some
	templates ---- OH YEAH That's because it's meant to be a simple process!
	
	I'll make it a bit less simple this time. I want to create a workflow
	where you can possibly put some data in, maybe go to another page to
	search for and select a contact, then come back and the relevant bits
	are kept track of.
	
	In any normal web application, that would call for session storage.
	This is no normal web application. It's running locally. There is
	(presumably) only one user. Session storage is just the global scope.
	Or perhaps class scope.
	
	PS: Yes, this has the kludge nature. Maybe it gets less weird in a
	"suspendable formlet"? Well, that's not written yet. And it might not be
	the right design. Time will tell.
	"""
	ELEMENTS = {
		'date': forms.Entry(type='date', lens=forms.DATE),
		'description': forms.Memo(lens=forms.BLANKABLE, style='width:100%'),
	}
	
	SESSION = {}
	
	def blank(self):
		return {
			'appointment':None, 'contact':None,
	        'date':datetime.date.today(),
		}
	
	def __init__(self, appt:str=None):
		super().__init__(self.ELEMENTS)
		if appt is None:
			if not self.SESSION:
				self.SESSION.update(self.blank())
			else:
				self.SESSION['appointment'] = None
		else:
			appointment=int(appt)
			if self.SESSION.get('appointment') != appointment:
				Q("select * from appointment where appointment=?", [appointment])
				self.SESSION.update(next(cursor))
		
	def get_native(self) -> dict:
		return self.SESSION
	
	def display(self, fields: dict, errors: dict) -> Response:
		contact = self.SESSION['contact']
		if contact is None:
			c_string = "Click to Choose..."
		else:
			Q("select * from contact where contact=?", [contact])
			row = next(cursor)
			c_string = row['name']
		return tpl('appt_form')(errors=errors, **fields, contact=c_string)
	
	def semantic_checks(self, native: dict, errors: dict):
		"""
		Let's do a check that you can't make new appointments in the past.
		For the moment, I'm not going to worry much about the case of changing
		existing appointments into the past; that requires a bit more guff.
		"""
		if native['date'] is None:
			errors['date'] = "You can't very well have an appointment that never happens."
		elif self.SESSION['appointment'] is None and native['date'] < datetime.date.today():
			errors['date'] = 'is in the past. That will never do.'
			
	def save(self, native: dict, request: Request) -> Response:
		self.SESSION.update(native)
		if 'contact' in request.POST: return Response.redirect('/contact')
		else:
			with connection:
				appt = self.SESSION.pop('appointment')
				if appt is None: insert('appointment', self.SESSION)
				else: update('appointment', assign=self.SESSION, where={'appointment':appt})
			self.SESSION.clear()
			return Response.redirect('/')

@app.function('/with_contact/*')
def with_contact(contact_id):
	"""
	I needed a way to connect the chosen contact up to an appointment session.
	This is probably deeply flawed, but it's also past midnight...
	
	More to the point, it shows that "work-flow" ideas still need thought.
	"""
	AppointmentForm.SESSION['contact'] = int(contact_id) if contact_id else None
	a = AppointmentForm.SESSION.get('appointment')
	appointment = 'new' if a is None else str(a)
	return Response.redirect('/appt/'+appointment)

@app.function('/appt/')
def sorry():
	return Response.generic(tpl('sorry')())

def transaction_wrapper(request:Request)->Response:
	try: response = app(request)
	except:
		if connection.in_transaction: connection.rollback()
		raise
	else:
		if connection.in_transaction:
			connection.rollback()
			return Response.swear(request, "I rolled back an uncommitted transaction.")
	return response

serve_http(tpl.wrap(transaction_wrapper))
