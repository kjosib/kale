<extend>page
<?title?>Add/Edit Task
<?body?>
	<ul>{errors}</ul>
<form method="post">
	<table>
		<tr><th>Complete?</th><td>{complete}</td></tr>
		<tr><th>Priority</th><td>{priority}</td></tr>
		<tr><th>Title</th><td>{title}</td></tr>
		<tr><th>Due Date</th><td>{due}</td></tr>
		<tr><th>Memo</th><td>{memo}</td></tr>
	</table>
<input type="submit" value="Save" />
</form>
</extend>
