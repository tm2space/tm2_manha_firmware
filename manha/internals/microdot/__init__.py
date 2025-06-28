import gc

gc.collect()

from .microdot import Microdot, Request, Response, abort, redirect, \
    send_file  # noqa: F401
