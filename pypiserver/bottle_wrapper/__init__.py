"""
This `__init__.py` allows to wrap and patch the default `bottle.py` implementation.
"""

from pypiserver.bottle_wrapper.bottle import *

BaseRequest.MEMFILE_MAX = 2**20
