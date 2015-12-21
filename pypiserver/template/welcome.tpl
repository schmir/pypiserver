<html><head><title>Welcome to pypiserver!</title></head><body>
<h1>Welcome to pypiserver!</h1>
<p>This is a PyPI compatible package index serving {{NUMPKGS}} packages.</p>

<p> To use this server with pip, run the the following command:
<blockquote><pre>
pip install --extra-index-url {{URL}}simple/ PACKAGE [PACKAGE2...]
</pre></blockquote></p>

<p> To use this server with easy_install, run the the following command:
<blockquote><pre>
easy_install -i {{URL}}simple/ PACKAGE
</pre></blockquote></p>

<p>Pretty interface web for search on <a href="{{PYPI}}">{{PYPI}}</a></p>

<p>The complete list of all packages can be found <a href="{{PACKAGES}}">here</a>
or via the <a href="{{SIMPLE}}">simple</a> index.</p>

<p>This instance is running version {{VERSION}} of the
  <a href="http://pypi.python.org/pypi/pypiserver">pypiserver</a> software.</p>
<p>
</body></html>
