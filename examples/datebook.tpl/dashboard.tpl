<extend>page
<?title?>Dashboard
<?body?>
<div class="w3-cell-row">
	<div class="w3-container w3-yellow w3-cell">
		<p>Appointments This Week:</p>
		<table class="w3-table w3-striped w3-bordered w3-border w3-hoverable">
			<thead><tr class="w3-light-grey"><th>Date</th><th>Description</th><th>Contact</th></tr></thead>
			{appt}
		</table>
		<p><a class="w3-button w3-blue w3-round-large" href="/appt/new">Click to add an appointment.</a></p>
	</div>
	<div class="w3-container w3-blue w3-cell">
		<p>Things to Do:</p>
		<table class="w3-table w3-striped w3-bordered w3-border w3-hoverable">
			<thead><tr class="w3-light-grey">
				<th><a href="task/sort/priority">Priority</a></th>
				<th>Description</th>
				<th><a href="task/sort/due">Due</a></th>
			</tr></thead>
			<tbody style="color:black">{task}</tbody>
		</table>
		<p><a class="w3-button w3-yellow w3-round-large" href="/task/new">Click to add a task.</a></p>
	</div>
</div>
</extend>
