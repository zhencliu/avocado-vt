import logging

from .images import get_image_handler


LOG = logging.getLogger("avocado.service." + __name__)


class _ImageAgent(object):

    def __init__(self):
        pass

    def info_image(self, image_config):
        return image_config

    def update_image(self, image_config, update_config):
        cmd, arguments = update_config.popitem()
        image_type = image_config["meta"]["type"]
        handler = get_image_handler(image_type, cmd)
        handler(image_config, arguments)


image_agent = _ImageAgent()
