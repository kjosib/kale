<extend>page
<?title?>Add/Edit Contact
<?body?>
	<ul>{errors}</ul>
<form method="post">
	<div style="display:flex">
		<label for="name" >Name:</label>{name}
		<label for="phone">Phone:</label>{phone}
		<label for="email">E-Mail:</label>{email}
	</div>
	<div style="display:flex">
		<div style="flex:1">
			<label for="address">Address:</label><br/>
			{address}
		</div>
		<div style="flex:1">
			<label for="memo">Memo:</label><br/>
			{memo}
		</div>
	</div>
<input type="submit" value="Save" />
</form>
</extend>
