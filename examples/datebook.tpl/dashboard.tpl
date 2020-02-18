<extend>page
<?title?>Dashboard
<?body?>
<div class="w3-cell-row">
	<div class="w3-container w3-yellow w3-cell">
		<p>Appointments This Week:</p>
			{appt}
		<p><a class="w3-button w3-blue w3-round-large" href="/appt/new">Click to add an appointment.</a></p>
	</div>
	<div class="w3-container w3-blue w3-cell">
		<p>Things to Do:</p>
		{task}
		<p><a class="w3-button w3-yellow w3-round-large" href="/task/new">Click to add a task.</a></p>
	</div>
</div>
</extend>
