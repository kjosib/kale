-- This simple script gets referenced in the datebook example.

create table if not exists contact (
	contact integer primary key,
	name text not null,
	address text,
	phone text,
	email text,
	memo text
);
create table if not exists appointment (
	appointment integer primary key,
	contact integer references contact,
	date date not null,
	description text
);
create table if not exists task (
	task integer primary key,
	priority int check (priority in (1,2,3)),
	complete boolean check (complete in (0,1)),
	title text not null,
	memo text,
	due date null
);
create index if not exists contact_name on contact(name);
create index if not exists apt_date on appointment(date);
create index if not exists task_due on task(due) where not complete;
create index if not exists task_cpl on task(complete);
