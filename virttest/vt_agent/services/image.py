import logging

from agents import image_agent
from services.resource import info_backing


LOG = logging.getLogger("avocado.service." + __name__)


def info_image(image_config):
    """
    Get all the configuration of the image.

    This function will call info_backing to get the volume's configuration
    """
    def _update_dict(src, new):
        for k, v in new.items():
            if k not in src:
                # a new key, add it
                src[k] = v
            else:
                # an existed key
                if isinstance(v, dict):
                    # a dict value, update the dict
                    _update_dict(src[k], v)
                elif not src[k]:
                    # assign the new value if source is not assigned
                    src[k] = v
                else:
                    # we should not be here
                    raise

    def _update_config(config, new_config):
        if "meta" in new_config:
            _update_dict(config["meta"], new_config["meta"])
        if "spec" in new_config:
            _update_dict(config["spec"], new_config["spec"])

    for virt_image_config in image_config["spec"]["virt-images"].values():
        volume_config = virt_image_config["spec"]["volume"]
        backing_id = volume_config["meta"]["backing"]
        backing_config = info_backing(backing_id)
        _update_config(volume_config, backing_config)

    return image_config


def update_image(image_config, config):
    """
    Update the upper-level image.

    For a qemu image, this function mainly executes qemu-img command,
    such as create/rebase/commit etc.
    """
    # Get all the configuration of the image
    LOG.info(f"Update image: {config}")
    image_agent.update_image(image_config, config)
