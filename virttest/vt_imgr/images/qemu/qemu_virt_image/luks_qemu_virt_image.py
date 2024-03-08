import os

from virttest.utils_misc import generate_random_string

from .qemu_virt_image import _QemuVirtImage


class _LuksQemuVirtImage(_QemuVirtImage):
    _VIRT_IMAGE_FORMAT = "luks"

    @classmethod
    def _define_config_legacy(cls, image_name, image_params, node_tags):
        config = super()._define_config_legacy(image_name, image_params, node_tags)
        spec = config["spec"]
        spec.update({
            "preallocation": image_params.get("preallocated"),
            "extent_size_hint": image_params.get("image_extent_size_hint"),
        })

        spec["encryption"].update({
            "name": "secret_{s}".format(s=generate_random_string(6)),
            "data": image_params.get("image_secret", "redhat"),
            "format": image_params.get("image_secret_format", "raw"),
            "stored": image_params.get("image_secret_stored", "data"),
            "file": None,
            "type": "luks",
            "object": "secret",
        })

        return config
