<loop>
			<table class="w3-table w3-striped w3-bordered w3-border w3-hoverable">
			<thead><tr class="w3-light-grey"><th>Date</th><th>Description</th><th>Contact</th></tr></thead>

<?begin?>
	<tr onclick="document.location='/appt/{appointment}'" class="active_row">
		<th>{date}</th>
		<td>{description}</td>
		<td>{name}</td>
	</tr>
<?end?>
			</table>
<?else?>
	<p>Zero.</p>
</loop>
