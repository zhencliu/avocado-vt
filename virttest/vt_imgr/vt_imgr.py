"""
The upper-level image manager.

from virttest.vt_imgr import vt_imgr

# Define the image configuration
image_config = vt_imgr.define_image_config(image_name, params, node_tags)

# Create the upper-level image object
image_id = vt_imgr.create_image_object(image_config)

# qemu-img create
vt_imgr.update_image(image_id, {"create":{"nodes": node_tags}})

# Query the summary config of the "image1"
vt_imgr.query_image(image_id, query="config", verbose=False)
returned:
  {"meta": {"uuid": "uuid-sn"
            "name": "sn",
            "type": "qemu",
            "topology": {"chain": ["base", "sn"]}},
   "spec": {"images": {"base": {"meta": {},
                                "spec": {"format": "raw",
                                         "volume": "volume-uuid1"}},
                       "sn": {"meta": {},
                              "spec": {"format": "qcow2",
                                       "volume": "volume-uuid2"}
                            }
                     }
           }
  }
"""
import logging

from .images import get_image_class

LOG = logging.getLogger("avocado." + __name__)


# TODO:
# Add drivers for diff handlers
# Add access permission for images
# serialize
class _VTImageManager(object):

    def __init__(self):
        self._images = dict()

    def startup(self):
        LOG.info("Start the image manager")

    def teardown(self):
        LOG.info("Stop the image manager")

    def define_image_config(self, image_name, params, node_tags):
        """
        Define the upper-level image(e.g. in the context of a VM, it's
        mapping to a VM's disk) configuration by its cartesian params.
        E.g. An upper-level qemu image has an lower-level image chain
            base ---> sn
              |        |
           resource resource
        :param image_name: The image tag defined in cartesian params,
                           e.g. for a qemu image, the tag should be the
                           top image("sn" in the example above) if the
                           "image_chain" is defined, usually it is
                           defined in the "images" param, e.g. "image1"
        :type image_name: string
        :param params: The params for all the lower-level images
                       Note it's *NOT* an image-specific params like
                         params.object_params("sn")
                       *BUT* the params for both "sn" and "base"
                       Examples:
                       1. images_vm1 = "image1 sn"
                          image_chain_sn = "base sn"
                          image_name = "sn"
                          params = the_case_params.object_params('vm1')
                       2. images = "image1 stg"
                          image_name = "image1"
                          params = the_case_params
        :type params: Params
        :param node_tags: The worker node tags, defined with cartesian param
                          "nodes". It means the image should be accessed from
                          these worker nodes
        :type node_tags: a list of string
        :return: The image configuration
        :rtype: dict
        """
        image_params = params.object_params(image_name)
        image_type = image_params.get("image_type", "qemu")
        image_class = get_image_class(image_type)
        return image_class.define_config(image_name, params, node_tags)

    def create_image_object(self, image_config):
        """
        Create an upper-level image(e.g. in the context of a VM, it's
        mapping to a VM's disk) object by its configuration without
        any storage allocation. All its lower-level images and their
        mapping storage resource objects will be created.
        :param image_config: The image configuration.
                             Call define_image_config to get it.
        :type image_config: dict
        :return: The image object id
        :rtype: string
        """
        LOG.debug(f"Create the image object for 'image_config[meta][name]'")
        image_type = image_config["meta"]["type"]
        image_class = get_image_class(image_type)
        image = image_class(image_config)
        image.create_object()
        self._images[image.image_id] = image
        return image.image_id

    def destroy_image_object(self, image_id):
        """
        Destroy a specified image. All its storage allocation should
        be released. Note if 'remove_image=no', then don't release the
        storage allocation.
        :param image_id: The image id
        :type image_id: string
        """
        image = self._images.get(image_id)
        LOG.debug(f"Destroy the image object for 'image.image_meta[name]'")
        image.destroy_object()
        if image.virt_images:
            LOG.info("Keep the image")
        else:
            del(self._images[image_id])

    def update_image(self, image_id, config):
        """
        Update a specified upper-level image

        config format:
          {command: arguments}

        Supported commands for a qemu image:
          create: qemu-img create
          destroy: Destroy the specified lower-level images
          resize: qemu-img resize
          map: qemu-img map
          convert: qemu-img convert
          commit: qemu-img commit
          snapshot: qemu-img snapshot
          rebase: qemu-img rebase
          add: Add a lower-level image object
          delete: Delete a lower-level image object

          Note: Not all images support the above operations
        The arguments is a dict object which contains all related settings
        for a specific command
        :param image_id: The image id
        :type image_id: string
        """
        LOG.debug(f"Update image: '{config}'")
        image = self._images.get(image_id)
        cmd, arguments = config.popitem()
        image_handler = image.get_image_handler(cmd)
        image_handler(arguments)

    def backup_image(self, image_id):
        image = self._images.get(image_id)
        image.backup()

    def query_image(self, image_id, request=None, verbose=False):
        """
        Query the configuration of a specified upper-level image, the
        general format of the image configuration:
          {"meta": {"uuid": "zzz"
                    "name": "xxx",
                    "type": "yyy"
                    "topology": {}},
           "spec": {"virt-images":{}}
          }
        E.g. A qemu image having an image chain:
          {"meta": {"uuid": "uuid-sn"
                    "name": "sn",
                    "type": "qemu",
                    "topology": {"chain": ["base", "sn"]}},
           "spec": {"virt-images": {"base": {"meta": {},
                                        "spec": {"format": "raw",
                                                 "volume": {"meta": {"uuid": "id1"},
                                                            "spec": {"size": 5678}}
                                                }
                                       },
                               "sn": {"meta": {},
                                      "spec": {"format": "qcow2",
                                               "volume": {"meta": {"uuid": "id2"},
                                                          "spec": {"size": 5678}}
                                              }
                                     }
                             }
                   }
          }
        :param request: The query content, format:
                        None
                        meta[.<key>]
                        spec[.virt-images.<image_name>[.meta[.<key>]]]
                        spec[.virt-images.<image_name>[.spec[.<key>]]]
                      Note the prefix "config.spec.virt-images" can omitted when
                      querying a specific <image_name>'s configuration:
                        <image_name>[.meta[.<key>]]
                        <image_name>[.spec[.<key>]]
                      Examples:
                        1. Query the image's configuration
                          request=None
                        2. Query the image's lower images' configurations
                          request=spec.virt-images
                        3. Query sn's volume configuration
                          request=spec.virt-images.sn.spec.volume
        :type request: string
        :param verbose: False: Return a summary of the configuration
                        True: Return all the configuration
        :type verbose: boolean
        :return: The upper-level image's configuration, or a snippet of
        :rtype: dict
        """
        image = self._images.get(image_id)
        return image.query(request, verbose)


vt_imgr = _VTImageManager()
