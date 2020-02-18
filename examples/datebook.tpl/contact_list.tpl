<loop>
	<table class="w3-table w3-striped w3-bordered w3-border w3-hoverable">
		<thead><tr class="w3-light-grey">
			<th width="10%"/>
			<th>Name</th>
			<th>Phone</th>
			<th>E-Mail</th>
		</tr></thead>
<?begin?>
		<tr onclick="document.location='/contact/{contact}'">
			<td><a href="/appt/new?contact={contact}" class="w3-button w3-yellow w3-border-blue w3-round-large w3-tiny w3-hover-purple">Appointment</a></td>
			<th>{name}</th>
			<td>{phone}</td>
			<td>{email}</td>
		</tr>
<?end?>
	</table>
<?else?>
	<p>You don't have any contacts defined yet.</p>
</loop>
