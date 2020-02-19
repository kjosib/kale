<extend>page
<?title?>Add/Edit Appointment
<?body?>
	<ul>{errors}</ul>
<form method="post">
	<table>
		<tr>
			<td>{date}</td>
			<td><input type="submit" name="contact" class="w3-button w3-blue w3-round-large" value="{contact}" /></td>
		</tr>
		<tr>
			<td colspan="2">{description}</td>
		</tr>
	</table>
<input type="submit" value="Save" />
</form>
</extend>
