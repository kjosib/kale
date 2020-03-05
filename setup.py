"""
Packaging script for PyPI.
"""

import setuptools

exec(open('src/kali/version.py').read())

setuptools.setup(
	name='kali',
	author='Ian Kjos',
	author_email='kjosib@gmail.com',
	version=__version__,
	packages=['kali',],
	package_dir = {'': 'src'},
	description='Simple, reliable, single-threaded HTTP service in Python. Aimed at serving web application to localhost as alternative to desktop application development.',
	long_description=open('README.md').read(),
	long_description_content_type="text/markdown",
	url="https://github.com/kjosib/kali",
	classifiers=[
		"Programming Language :: Python :: 3.7",
		"License :: OSI Approved :: MIT License",
		"Operating System :: OS Independent",
		"Intended Audience :: Developers",
		"Development Status :: 3 - Alpha",
		"Environment :: Console",
		"Environment :: No Input/Output (Daemon)",
		"Environment :: Web Environment",
		"Topic :: Internet :: WWW/HTTP :: HTTP Servers",
    ],
	
)