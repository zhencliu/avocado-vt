import logging
import copy

from virttest.vt_cluster import cluster

from ..image import _Image
from .qemu_virt_image import get_virt_image_class


LOG = logging.getLogger("avocado." + __name__)


class _QemuImage(_Image):

    # The upper-level image type
    _IMAGE_TYPE = "qemu"

    def __init__(self, image_config):
        super().__init__(image_config)
        # Store images with the same order as tags defined in image_chain
        self._handlers = {
            "create": self.qemu_img_create,
            "destroy": self.qemu_img_destroy,
            "rebase": self.qemu_img_rebase,
            "commit": self.qemu_img_commit,
            "snapshot": self.qemu_img_snapshot,
            "add": self.add_virt_image,
            "remove": self.remove_virt_image,
        }

    @classmethod
    def _define_virt_image_config(cls, image_name, image_params, node_tags):
        image_format = image_params.get("image_format", "qcow2")
        virt_image_class = get_virt_image_class(image_format)
        return virt_image_class.define_config(image_name, image_params, node_tags)

    @classmethod
    def _define_config_legacy(cls, image_name, params, node_tags):
        def _define_topo_chain_config():
            for image_tag in image_chain:
                image_params = params.object_params(image_tag)
                virt_images[image_tag] = cls._define_virt_image_config(
                    image_tag, image_params, node_tags
                )

        def _define_topo_none_config():
            image_params = params.object_params(image_name)
            virt_images[image_tag] = cls._define_virt_image_config(
                image_name, image_params, node_tags
            )

        config = super()._define_config_legacy(image_name, params, node_tags)
        virt_images = config["spec"]["virt-images"]

        image_chain = params.object_params(image_name).objects("image_chain")
        if image_chain:
            config["meta"]["topology"] = {"chain": image_chain}
            _define_topo_chain_config()
        else:
            config["meta"]["topology"] = {"none": [image_name]}
            _define_topo_none_config()

        return config

    @property
    def image_access_nodes(self):
        node_set = set()
        for virt_image in self.virt_images.values():
            node_set.update(virt_image.virt_image_access_nodes)
        return list(node_set)

    @property
    def virt_images(self):
        return self._virt_images

    @property
    def virt_image_names(self):
        return list(self.image_meta["topology"].values())[0]

    def get_image_update_config(self, node_tag):
        config = copy.deepcopy(self.image_config)
        spec = config["spec"]
        if tag in self.virt_image_names:
            virt_image_config = spec["virt-images"][tag]
            volume_config = virt_image_config["spec"]["volume"]
            bindings = volume_config["meta"].pop("bindings")
            volume_config["meta"]["backing"] = bindings[node_tag]
        return config

    def _create_virt_image_object(self, virt_image_name):
        config = self.image_spec["virt-images"][virt_image_name]
        image_format = config["spec"]["format"]
        virt_image_class = get_virt_image_class(image_format)
        virt_image = virt_image_class(config)
        virt_image.create_object()
        return virt_image

    def create_object(self):
        """
        Create the qemu image object.
        All its lower-level virt image objects and their volume
        objects will be created
        """
        for virt_image_name in self.virt_image_names:
            self.virt_images[virt_image_name] = self._create_virt_image_object(virt_image_name)

    def destroy_object(self):
        """
        Destroy the image object, all its lower-level image objects
        will be destroyed.
        """
        for image_tag in self.virt_image_names[::-1]:
            virt_image = self.virt_images[image_tag]
            if not virt_image.keep():
                virt_image.destroy_object()
                self.virt_images.pop(image_tag)

    def query(self, request, verbose=False):
        pass

    def backup(self):
        pass

    def add_virt_image(self, arguments):
        tag = arguments["name"]
        image_params = arguments.pop('params')
        node_tags = arguments.pop("nodes")

        backing = arguments.pop("backing", None)
        if backing:
            if backing in self.virt_image_names:
                idx = self.virt_image_names.index(backing)
                self.virt_image_names.insert(idx+1, backing)
                if "none" in self.image_meta["topology"]:
                    self.image_meta["topology"]["chain"] = self.image_meta["topology"].pop("none")
            else:
                raise Exception(f"{backing} is not present in the image")

        self.image_spec["virt-images"][tag] = self._define_virt_image_config(
            tag, image_params, node_tags
        )
        self.virt_images[tag] = self._create_virt_image_object(tag)
        #self.virt_images[tag].allocate_volume(arguments)
        #node = cluster.get_node_by_tag(node_tags[0])
        self.qemu_img_create(arguments)
        #node.proxy.image.update_image(self.image_config,
        #                              {"add": arguments})

    def remove_virt_image(self, arguments):
        tag = arguments.pop('name')
        virt_image = self.virt_images[tag]
        virt_image.release_volume(arguments)
        if tag in self.virt_image_names:
            self.virt_image_names.remove(tag)
            if len(self.virt_image_names) < 2 and "none" not in self.image_meta["topology"]:
                _, self.image_meta["topology"]["none"] = self.image_meta["topology"].popitem()
        self.virt_images.pop(tag)

    def qemu_img_create(self, arguments):
        """
        qemu-img create

        Allocate storage by resource management system first.
        """
        LOG.info(f"Create image")
        image_tags = arguments.get("nodes") or self.virt_image_names
        for image_tag in image_tags:
            virt_image = self.virt_images[image_tag]
            virt_image.allocate_volume(arguments)

        node_tag = self.image_access_nodes[0]
        node = cluster.get_node_by_tag(node_tag)
        node.proxy.image.update_image(self.image_config,
                                      {"create": arguments})

    def qemu_img_destroy(self, arguments):
        """
        Release storage by resource management system.

        Note the image object still exists, i.e. all the lower-level
        image objects and their volume objects will not be destroyed.
        """
        LOG.info(f"Destroy image")
        for image_tag in self.virt_image_names[::-1]:
            virt_image = self.virt_images[image_tag]
            virt_image.release_volume(arguments)

    def qemu_img_rebase(self, arguments):
        node_tag = self.image_access_nodes[0]
        node = cluster.get_node_by_tag(node_tag)
        node.proxy.image.update_image(self.image_config,
                                      {"rebase": arguments})

    def qemu_img_commit(self, arguments):
        node_tag = self.image_access_nodes[0]
        node = cluster.get_node_by_tag(node_tag)
        node.proxy.image.update_image(self.image_config,
                                      {"commit": arguments})

    def qemu_img_snapshot(self, arguments):
        node_tag = self.image_access_nodes[0]
        node = cluster.get_node_by_tag(node_tag)
        node.proxy.image.update_image(self.image_config,
                                      {"snapshot": arguments})
