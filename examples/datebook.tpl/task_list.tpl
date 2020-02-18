<loop>
	<table class="w3-table w3-striped w3-bordered w3-border w3-hoverable">
		<thead><tr class="w3-light-grey">
			<th><a href="task/sort/priority">Priority</a></th>
			<th>Description</th>
			<th><a href="task/sort/due">Due</a></th>
		</tr></thead>
		<tbody style="color:black">
<?begin ?>
			<tr onclick="document.location='/task/{task}'" class="active_row">
				<th>{priority}</th>
				<td>{title}</td>
				<td>{due}</td>
			</tr>
<?end ?>
		</tbody>
	</table>
<?else ?>
	<p>There are not any tasks yet.</p>
</loop>

