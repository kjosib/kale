"""
<html><body>
<p>
You'll probably want to supply a stylesheet. Perhaps some javascript library.
Maybe even some images. One way or another, it's handy to be able to point at
a directory full of static content and let the framework do its job.
</p>

<p>
This example exercises that facility by presenting the examples folder within
your web browser.
</p>

<p>Click <a href="static">here</a> to see this work.</p>
</body></html>
"""

import os
import kale

app = kale.Router()

# This is how it's done:
app.delegate_folder("/static/", kale.StaticFolder(os.path.dirname(__file__)))


# This is enough to have an index page.
@app.function('/')
def hello(): return __doc__

kale.serve_http(app)
