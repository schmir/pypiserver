#! /usr/bin/env python3
"""Entrypoint for pypiserver."""

import importlib
import logging
import sys
import typing as t
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler

import functools as ft
from pypiserver.config import Config, UpdateConfig

if t.TYPE_CHECKING:
    import pypiserver.bottle  # noqa pylint: disable=unused-import


log = logging.getLogger("pypiserver.main")


def init_logging(
    level: int = logging.NOTSET,
    frmt: str = None,
    filename: t.Union[str, Path] = None,
    stream: t.Optional[t.IO] = sys.stderr,
    logger: logging.Logger = None,
) -> None:
    """Configure the specified logger, or the root logger otherwise."""
    logger = logger or logging.getLogger()
    logger.setLevel(level)

    formatter = logging.Formatter(frmt)
    if len(logger.handlers) == 0 and stream is not None:
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        logger.addHandler(logging.StreamHandler(stream))

    if filename:
        handler = logging.FileHandler(filename)
        handler.setFormatter(formatter)
        logger.addHandler(handler)


class WsgiHandler(WSGIRequestHandler):
    """A simple request handler to configure logging."""

    # The default `FixedHandler` that bottle's `WSGIRefServer` uses does not
    # log in a particularly predictable or configurable way. We'll pass this
    # in to use instead.
    def address_string(self) -> str:  # Prevent reverse DNS lookups please.
        # This method copied directly from bottle's `FixedHandler` and
        # maintained on the Chesterton's fence principle (i.e. I don't know
        # why it's important, so I'm not going to get rid of it)
        return self.client_address[0]

    def log_message(
        self, format: str, *args: t.Any  # pylint: disable=redefined-builtin
    ) -> None:
        """Log a message."""
        # The log_message method on the `HttpRequestHandler` base class just
        # writes directly to stderr. We'll use its same formatting, but pass
        # it through the logger instead.
        log.info(
            "%s - - [%s] %s\n",
            self.address_string(),
            self.log_date_time_string(),
            format % args,
        )


class ServerCheck:
    """Methods to check for a server's presence in the import path."""

    # Because we need to potentially override behavior for different servers
    # by passing options into bottle's `run` method, and because those options
    # aren't necessarily compatible between servers, we need to be able to guess
    # which server bottle will pick if the user specifies the `auto` server
    # type. These methods' names match the `__name__` property of the server
    # adapters in bottle, so we can filter the adapters on the `AutoServer`
    # adapter to figure out which ones are present. Since bottle uses the
    # first server to successfully import from that same list, this should
    # be sufficient to give us good certainty as to which server it will run.

    # pylint: disable=missing-function-docstring
    # pylint: disable=invalid-name
    # pylint: disable=import-outside-toplevel
    # pylint: disable=unused-import

    @staticmethod
    def can_import(name: str) -> bool:
        """Attempt to import a module. Return a bool indicating success."""
        try:
            importlib.import_module(name)
            return True
        except ImportError:
            return False

    @classmethod
    def WaitressServer(cls) -> bool:
        return cls.can_import("waitress")

    @classmethod
    def PasteServer(cls) -> bool:
        return cls.can_import("paste")

    @classmethod
    def TwistedServer(cls) -> bool:
        return cls.can_import("twisted.web")

    @classmethod
    def CherryPyServer(cls) -> bool:
        if cls.can_import("cheroot.wsgi"):
            return True
        return cls.can_import("cherrypy.wsgiserver")

    @classmethod
    def WSGIRefServer(cls) -> bool:
        return cls.can_import("wsgiref")

    # pylint: enable=missing-function-docstring
    # pylint: enable=invalid-name
    # pylint: enable=import-outside-toplevel
    # pylint: enable=unused-import


def guess_auto_server() -> "t.Type[pypiserver.bottle.ServerAdapter]":
    """Guess which server bottle will use for the auto setting."""
    # pylint: disable=import-outside-toplevel
    import pypiserver.bottle  # pylint: disable=redefined-outer-name

    # Return the first ServerAdapter in `AutoServer.adapters` whose
    # corresponding method in `ServerCheck` returns True.
    server = next(
        filter(
            lambda s: getattr(ServerCheck, s.__name__)(),
            pypiserver.bottle.AutoServer.adapters,
        ),
        None,
    )
    if server is None:
        raise RuntimeError(
            "Unexpected error determining bottle auto server. There may be an "
            "issue with this python environment. Please report this bug at "
            "https://github.com/pypiserver/pypiserver/issues"
        )
    return server


def main(argv: t.Sequence[str] = None) -> None:
    """Application entrypoint for pypiserver.

    This function drives the application (as opposed to the library)
    implementation of pypiserver. Usage from the commandline will result in
    this function being called.
    """
    # pylint: disable=import-outside-toplevel
    import pypiserver  # pylint: disable=redefined-outer-name

    if argv is None:
        # The first item in sys.argv is the name of the python file being
        # executed, which we don't need
        argv = sys.argv[1:]

    config = Config.from_args(argv)

    init_logging(
        level=config.log_level,
        filename=config.log_file,
        frmt=config.log_frmt,
        stream=config.log_stream,
    )

    # Check to see if we were asked to run an update command instead of running
    # the server
    if isinstance(config, UpdateConfig):
        from pypiserver.manage import update_all_packages

        update_all_packages(
            config.roots,
            config.download_directory,
            dry_run=not config.execute,
            stable_only=config.allow_unstable,
            ignorelist=config.ignorelist,
        )
        return

    # Fixes #49:
    #    The gevent server adapter needs to patch some
    #    modules BEFORE importing bottle!
    if config.server_method.startswith("gevent"):
        import gevent.monkey  # @UnresolvedImport

        gevent.monkey.patch_all()

    from pypiserver import bottle

    bottle.debug(config.verbosity > 1)
    bottle._stderr = ft.partial(  # pylint: disable=protected-access
        _logwrite, logging.getLogger(bottle.__name__), logging.INFO
    )

    # Here `app` is a Bottle instance, which we pass to bottle.run() to run
    # the server
    app = pypiserver.app_from_config(config)

    if config.server_method == "gunicorn":
        # When bottle runs gunicorn, gunicorn tries to pull its arguments from
        # sys.argv. Because pypiserver's arguments don't match gunicorn's,
        # this leads to errors.
        # Gunicorn can be configured by using a `gunicorn.conf.py` config file
        # or by specifying the `GUNICORN_CMD_ARGS` env var. See gunicorn
        # docs for more info.
        sys.argv = ["gunicorn"]

    wsgi_kwargs = {"handler_class": WsgiHandler}

    if config.server_method == "auto":
        expected_server = guess_auto_server()
        extra_kwargs = (
            wsgi_kwargs if expected_server is bottle.WSGIRefServer else {}
        )
        log.debug(
            "Server 'auto' selected. Expecting bottle to run '%s'. "
            "Passing extra keyword args: %s",
            expected_server.__name__,
            extra_kwargs,
        )
    else:
        extra_kwargs = wsgi_kwargs if config.server_method == "wsgiref" else {}
        log.debug(
            "Running bottle with selected server '%s'", config.server_method
        )

    bottle.run(
        app=app,
        host=config.host,
        port=config.port,
        server=config.server_method,
        **extra_kwargs,
    )


def _logwrite(logger, level, msg):
    if msg:
        line_endings = ["\r\n", "\n\r", "\n"]
        for le in line_endings:  # pylint: disable=invalid-name
            if msg.endswith(le):
                msg = msg[: -len(le)]
        if msg:
            logger.log(level, msg)


if __name__ == "__main__":
    main()
