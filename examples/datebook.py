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
	return tpl('appt_row').each(cursor)

def pending_tasks():
	order = {
		'priority': "priority asc, ifnull(due, '9999-99-99') asc",
		'due': "ifnull(due, '9999-99-99') asc, priority asc",
	}[STATE['task_order']]
	Q("select * from task where not complete order by "+order)
	return tpl('task_row').each(cursor)

@app.function('/task/sort/*')
def set_task_sort_order(order):
	assert order in ('priority', 'due')
	STATE['task_order'] = order
	return Response.redirect("/")

# An application like this needs some way to enter data.
# Let's start with something for to-do list entries:
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
def list_contacts(q=''):
	if q:
		Q(
			"select * from contact where name like ? or address like ? or memo like ? order by name",
			['%'+q+'%']*3
		)
	else:
		Q("select * from contact order by name")
	return tpl('contact_home')(
		q=q,
		rows = tpl('contact_row').each(cursor)
	)


@app.servlet('/contact/new')
@app.servlet('/contact/*')
class ContactForm(forms.Formlet):
	"""
	If you think about it, the "Add" and "Edit" functionality is extremely
	similar. The same `Formlet` subclass can handle both cases. It's up to
	you which approach you prefer.
	"""
	def __init__(self, contact_id=None):
		self.contact_id = int(contact_id) if contact_id else None
		super().__init__(CONTACT_ELEMENTS)
	
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


@app.function('/appt/new')
@app.function('/appt/')
def sorry_not_yet(contact=None):
	return Response.generic(tpl('sorry')())


PRIORITIES = forms.EnumLens(['High', 'Medium', 'Low'], base=1)
YES_NO = forms.EnumLens(['No', 'Yes',], reverse=True)

TASK_ELEMENTS = {
	'priority': forms.Pick(PRIORITIES, required='Please select a priority.'),
	'complete': forms.Pick(YES_NO, required="So is it complete or not?"),
	'title': forms.Entry(),
	'memo': forms.Memo(lens=forms.BLANKABLE),
	'due': forms.Entry(type='date', lens=forms.NULLABLE), # Technically we should perform date-validation...
}

PHONE = forms.Test(r'[-,;0-9()/]*', error='can contain only numbers and ()-,;/ characters.')
EMAIL = forms.Test(r'|\S*@\S+\.[a-zA-Z]+', error='does not look much like an e-mail address.')

CONTACT_ELEMENTS = {
	'name': forms.Entry(style='flex:1'),
	'phone': forms.Entry(lens=PHONE, style='flex:1'),
	'email': forms.Entry(lens=EMAIL, style='flex:1'),
	'address': forms.Memo(lens=forms.BLANKABLE, style='width:100%'),
	'memo': forms.Memo(lens=forms.BLANKABLE, style='width:100%'),
}

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
