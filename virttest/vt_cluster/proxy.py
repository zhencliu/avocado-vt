# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2022
# Authors: Yongxue Hong <yhong@redhat.com>

"""
This module provides VT Proxy interfaces.
"""

import importlib
import importlib.util
import logging
import sys
from xmlrpc import client

from ..vt_agent import core as vt_agent_core
from . import ClusterError

LOG = logging.getLogger("avocado." + __name__)


class ServerProxyError(ClusterError):
    """Generic Server Proxy Error."""

    def __init__(self, code, message):
        self.code = code
        self.message = message


class _ClientMethod:
    def __init__(self, send, name):
        self.__send = send
        self.__name = name

    def __getattr__(self, name):
        return _ClientMethod(self.__send, "%s.%s" % (self.__name, name))

    def __call__(self, *args):
        root_mod = None
        exc_type = None
        try:
            return self.__send(self.__name, args)
        except client.Fault as e:
            if "." in e.faultCode[0]:
                root_mod = ".".join(e.faultCode[0].split(".")[:-1])
                exc_type = e.faultCode[0].split(".")[-1]
            kargs = e.faultCode[1]
            root_mod = importlib.import_module(root_mod)
            try:
                if isinstance(kargs, dict):
                    # TODO: Can not ensure initialize the any Exception here
                    raise getattr(root_mod, exc_type)(**kargs)
                elif isinstance(kargs, str):
                    raise eval(e.faultCode[0])(kargs)
            except Exception:
                raise ServerProxyError(e.faultCode, e.faultString)


class _ClientProxy(client.ServerProxy):
    def __init__(self, uri):
        super(_ClientProxy, self).__init__(uri, allow_none=True, use_builtin_types=True)

    def __getattr__(self, name):
        return _ClientMethod(self._ServerProxy__request, name)


class _LocalProxy(object):
    def __init__(self):
        # Rename the virttest.vt_agent as vt_agent for the local node import it
        if "vt_agent" not in sys.modules:
            module_name = "vt_agent"
            agent_module = importlib.import_module("virttest.vt_agent")
            sys.modules[module_name] = agent_module
        self._services = vt_agent_core.service.load_services()

    def __getattr__(self, name):
        return importlib.import_module("virttest.vt_agent.services.%s" % name)


def get_server_proxy(uri=None):
    """
    Get the server proxy.

    :param uri: The URI of the server proxy.
                e.g:
    :type uri: str
    :return: The proxy obj.
    :rtype: _ClientProxy or _LocalProxy
    """
    return _ClientProxy(uri) if uri else _LocalProxy()