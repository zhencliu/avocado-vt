import os

from avocado.utils.path import init_dir
from ...pool_connection import _ResourcePoolConnection


class _DirPoolConnection(_ResourcePoolConnection):

    _CONNECT_POOL_TYPE = "filesystem"

    def __init__(self, pool_config):
        super().__init__(pool_config)
        self._root_dir = pool_config["spec"]["path"]

    def startup(self):
        init_dir(self.root_dir)

    def shutdown(self):
        if not os.listdir(self.root_dir):
            os.removedirs(self.root_dir)

    @property
    def connected(self):
        return os.path.exists(self.root_dir)

    @property
    def root_dir(self):
        return self._root_dir

    @property
    def info(self):
        return dict()