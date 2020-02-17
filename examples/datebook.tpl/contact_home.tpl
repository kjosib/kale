<extend>page
<?title?>Contacts
<?body?>
<p><a class="w3-button w3-yellow w3-round-large" href="/contact/new">Click to add a contact.</a></p>
<p><form method="get"><label for="q">Search:</label><input type="text" name="q" value="{q}" /><input type="submit"/></form></p>
<table class="w3-table w3-striped w3-bordered w3-border w3-hoverable">
	<thead><tr class="w3-light-grey">
		<th width="10%"/>
		<th>Name</th>
		<th>Phone</th>
		<th>E-Mail</th>
	</tr></thead>
	{rows}
</table>
