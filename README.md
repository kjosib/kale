# kale
Simple, reliable, single-threaded HTTP service in Python. Aimed at serving web application to localhost as alternative to desktop application development.

I wanted to expose a SINGLE-THREADED WEB APPLICATION over HTTP to LOCALHOST ONLY.
Web application, because it's a comfortable style of working with data entry and navigation.
Single threaded, to support working well with SQLite, which doesn't play well with multi-threading,
and Windows, which is not particularly suited to a forking-model server.

Web browsers lately all expect to open multiple connections and might not send the first request on
the first connection. The Python Standard Library offers class "HttpServer", but as currently coded,
it only works properly when you're using a forking or threading mix-in. In sequential-service mode,
the standard library deadlocks (at least until the end user refreshes the browser a few times).

The essential problem is solved by setting a brief time-out on the first packet from the client.
If that time-out expires, the connection is closed and the server accepts the next caller, which
will generally have the request data from the browser. The server also only speaks HTTP/1.0 on
purpose: it guarantees all requests are served in a timely manner. There is zero packet latency
on localhost, so there's not a real performance drain here.

So long as I'm re-inventing the wheel, I might as well do it with the end in sight.
Therefore:

1. The server is a higher-order function: you pass in a handler function.
	The handler function must accept a `Request` object and return -- something: ideally
	a `Response` object, but in practice a suitable content body will do. There are some
	convenience methods for creating redirections, serving plain text, etc.

2. This means routing requests to different response methods is a separate problem.
	You could write a function which reads the path component of the `Request` URI to
	decide which of many sub-functions to call, and which bits of the path correspond
	to parameters, etc. In fact, any callable-object will do. In the abstract, we call
	that "routing a request" to the correct handler.

3. It's really annoying forgetting to commit-or-rollback a transaction in a handler.
	Changes may appear fine locally (until they vanish) but nobody else sees anything
	except a locked database. Checking for this a simple matter by wrapping the root
	handler (application router) and taking corrective measures. (Roll back the
	transaction and return an error response maybe.)

4. The framework takes (some) pains to avoid excessive copying, drawing inspiration from the
	iolist facility in the Erlang ecosystem. Rather than building up a big string, supply
	a list of them, or a funny-shaped nest of them, etc. The rules are somewhat loose.

5. There's a simple HTML templating facility included: it will do the job without being
	accidentally quadratic. Much.
