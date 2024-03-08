from virttest.utils_misc import generate_random_string

from .qemu_virt_image import _QemuVirtImage


class _Qcow2QemuVirtImage(_QemuVirtImage):

    _VIRT_IMAGE_FORMAT = "qcow2"

    @classmethod
    def _define_config_legacy(cls, image_name, image_params, node_tags):
        config = super()._define_config_legacy(image_name, image_params, node_tags)
        spec = config["spec"]
        spec.update({
            "cluster-size": image_params.get("image_cluster_size"),
            "lazy-refcounts": image_params.get("lazy_refcounts"),
            "compat": image_params.get("qcow2_compatible"),
            "preallocation": image_params.get("preallocated"),
            "extent_size_hint": image_params.get("image_extent_size_hint"),
            "compression_type": image_params.get("image_compression_type"),
        })

        if image_params.get("image_encryption"):
            spec["encryption"] = {
                "name": "secret_{s}".format(s=generate_random_string(6)),
                "data": image_params.get("image_secret", "redhat"),
                "format": image_params.get("image_secret_format", "raw"),
                "stored": image_params.get("image_secret_stored", "data"),
                "file": None,
                "encrypt": {
                    "format": image_params["image_encryption"],
                },
                "object": "secret",
            }

        return config
