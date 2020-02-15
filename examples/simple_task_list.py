"""
<html><head>
<title>Oversimplified Non-persistent To-Do List Example</title>
<style>
	body {background: #eeffcc; }
	.complete {text-decoration: line-through; color:#cccccc}
	.todo {font-weight:bold}
	.nb {padding:15px; background:black; color:#ccccff}
</style>
</head>
<body>{.body}<p class="nb">

This simplified to-do list application exercises form data submissions,
servlets, etc. <br/>
It doesn't bother with persistent data storage because that's not the
point right now.

</p></body>
</html>
"""

import kali

app = kali.Router()

# For the sake of this example, I'll define a task as a pair of
# <boolean, string> with rather unsurprising semantics. Rather than
# go to the effort to gin up a database, I'll just use a list.
# Maybe in the next version
TO_DO = [
	(False, "Eat",),
	(False, "Sleep",),
	(True, "Breathe",),
	(False, "Save the world before bedtime",),
]

# Some HTML templates are appropriate for simple presentation.
# Here's a generic background page for the app.
page = kali.Template(__doc__)

# Surely there will be cause for display of a list of current items,
# and the ability to check them off as you go. To that end, let's have
# a couple of templates. But first....
kali.Template.REGISTRY[':class'] = ('todo', 'complete').__getitem__
# Note the middle line in the template below, what says "{state:class}".
# The bit above it what makes that work. In theory you could make nice
# formatting for numbers, or really whatever you like. Think of it like
# being able to add custom tags maybe? Anyway, back to the templates:
line = kali.Template("""
<li>
	[<a href="/task/{id}/toggle">toggle</a>]
	<span class="{state:class}">{text}</span>
	[<a href="/task/{id}/edit">edit</a>]
</li>
""")
todo_body = kali.Template("""
<p>Simple To-Do List:</p>
<ol>{.items}</ol>
<p><a href="new">New entry</a></p>
""")

# A simple root page just displays the current state of the list, along with the
# control links expressed by the templates.
@app.function("/")
def home():
	line_items = [line(id=index, state=state, text=task) for index, (state, task) in enumerate(TO_DO)]
	return page(body=todo_body(items = line_items))



# We need a simple form for adding tasks...
task_form = kali.Template("""
	<form method="post">
	<input type="text" name="task" value="{task}" />
	<input type="submit" value="{label}" />
	</form>
""")

# The simplest way to serve up a form is to register a servlet, as follows:
@app.servlet('/new')
class NewEntry:
	def do_GET(self, rq:kali.Request):
		return page(body=task_form(task="", label="Add Entry"))
	
	def do_POST(self, rq:kali.Request):
		# In a real application, you'd have some error checking here...
		task = rq.POST['task']
		if task: TO_DO.append((False, task))
		return kali.Response.redirect('/')

# Another alternative is a full-service ... service. Pun intended.
# This is sort of a multiplexed servlet: a closely related group of
# methods meant to work with the same business entity.
@app.service('/task/*/')
class TaskController:
	def __init__(self, task_id):
		self.id = int(task_id)
		
	def do_GET_toggle(self, rq:kali.Request):
		done, task = TO_DO[self.id]
		TO_DO[self.id] = (not done, task)
		return kali.Response.redirect('/')
	
	def do_GET_edit(self, rq:kali.Request):
		done, task = TO_DO[self.id]
		return page(body=task_form(task=task, label="Edit Entry"))
	
	def do_POST_edit(self, rq:kali.Request):
		done, task = TO_DO[self.id]
		if rq.POST['task']: TO_DO[self.id] = (done, rq.POST['task'])
		else: TO_DO.pop(self.id)
		return kali.Response.redirect('/')


# Don't forget to actually start the server.
kali.serve_http(app)

# Thanks for reading.
