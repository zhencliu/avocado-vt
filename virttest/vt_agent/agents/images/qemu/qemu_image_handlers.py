import collections
import logging
import json
import re
import string

from avocado.core import exceptions
from avocado.utils import path as utils_path
from avocado.utils import process

from virttest import utils_numeric


LOG = logging.getLogger("avocado.service." + __name__)


class _ParameterAssembler(string.Formatter):
    """
    Command line parameter assembler.

    This will automatically prepend parameter if corresponding value is passed
    to the format string.
    """

    sentinal = object()

    def __init__(self, cmd_params=None):
        string.Formatter.__init__(self)
        self.cmd_params = cmd_params or {}

    def format(self, format_string, *args, **kwargs):
        """Remove redundant whitespaces and return format string."""
        ret = string.Formatter.format(self, format_string, *args, **kwargs)
        return re.sub(" +", " ", ret)

    def get_value(self, key, args, kwargs):
        try:
            val = string.Formatter.get_value(self, key, args, kwargs)
        except KeyError:
            if key in self.cmd_params:
                val = None
            else:
                raise
        return (self.cmd_params.get(key, self.sentinal), val)

    def convert_field(self, value, conversion):
        """
        Do conversion on the resulting object.

        supported conversions:
            'b': keep the parameter only if bool(value) is True.
            'v': keep both the parameter and its corresponding value,
                 the default mode.
        """
        if value[0] is self.sentinal:
            return string.Formatter.convert_field(self, value[1], conversion)
        if conversion is None:
            conversion = "v"
        if conversion == "v":
            return "" if value[1] is None else " ".join(value)
        if conversion == "b":
            return value[0] if bool(value[1]) else ""
        raise ValueError("Unknown conversion specifier {}".format(conversion))


QEMU_IMG_BINARY = utils_path.find_command("qemu-img")
qemu_img_parameters = {
    "image_format": "-f",
    "backing_file": "-b",
    "backing_format": "-F",
    "unsafe": "-u",
    "options": "-o",
    "secret_object": "",
    "tls_creds_object": "",
    "image_opts": "",
    "check_repair": "-r",
    "output_format": "--output",
    "force_share": "-U",
    "resize_preallocation": "--preallocation",
    "resize_shrink": "--shrink",
    "convert_compressed": "-c",
    "cache_mode": "-t",
    "source_cache_mode": "-T",
    "target_image_format": "-O",
    "convert_sparse_size": "-S",
    "rate_limit": "-r",
    "convert_target_is_zero": "--target-is-zero",
    "convert_backing_file": "-B",
    "commit_drop": "-d",
    "compare_strict_mode": "-s",
    "compare_second_image_format": "-F",
}
cmd_formatter = _ParameterAssembler(qemu_img_parameters)


def _get_base_image(image_tag, topology):
    base = None
    topo, images = list(topology.items())[0]

    if topo == "chain":
        idx = images.index(image_tag)
        base = images[idx-1] if idx > 0 else None

    return base


def _get_dir_volume_info(volume_config):
    auth = None
    info = {
        "driver": "file",
        "filename": volume_config["spec"]["uri"],
    }

    return auth, info


def _get_nfs_volume_info(volume_config):
    auth = None
    info = {
        "driver": "file",
        "filename": volume_config["spec"]["uri"],
    }

    return auth, info


def _get_ceph_volume_info(volume_config):
    auth = dict()

    pool_config = volume_config["meta"]["pool"]
    pool_meta = pool_config["meta"]
    pool_spec = pool_config["spec"]

    volume_opts = {
        "driver": "rbd",
        "pool": pool_spec["pool"],
        "image": pool_spec["image"],
    }

    if pool_spec.get("conf") is not None:
        volume_opts["conf"] = pool_spec["conf"]
    if pool_spec.get("namespace") is not None:
        volume_opts["namespace"] = pool_spec["namespace"]

    return auth, volume_opts


def _get_iscsi_direct_volume_info(volume_config):
    auth = dict()

    pool_config = volume_config["meta"]["pool"]
    pool_meta = pool_config["meta"]
    pool_spec = pool_config["spec"]

    # required options for iscsi
    volume_opts = {
        "driver": "iscsi",
        "transport": pool_spec["transport"],
        "portal": pool_spec["portal"],
        "target": pool_spec["target"],
    }

    # optional option
    if pool_spec["user"] is not None:
        volume_opts["user"] = pool_spec["user"]

    return auth, volume_opts


def _get_nbd_volume_info(volume_config):
    auth = dict()

    volume_meta = volume_config["meta"]
    volume_spec = volume_config["spec"]
    pool_config = volume_meta["pool"]
    pool_meta = pool_config["meta"]
    pool_spec = pool_config["spec"]

    volume_opts = {"driver": "nbd"}
    if pool_spec.get("host"):
        volume_opts.update({
            "server.type": "inet",
            "server.host": pool_spec["host"],
            "server.port": volume_spec.get("port", 10809),
        })
    elif pool_spec.get("path"):
        volume_opts.update({
            "server.type": "unix",
            "server.path": pool_spec["path"],
        })
    else:
        raise

    if volume_spec.get("export"):
        volume_opts["export"] = volume_spec["export"]

    return auth, volume_opts


def get_qemu_virt_image_volume_info(volume_config):
    volume_info_getters = {
        "filesystem": _get_dir_volume_info,
        "nfs": _get_nfs_volume_info,
        "ceph": _get_ceph_volume_info,
        "iscsi-direct": _get_iscsi_direct_volume_info,
        "nbd": _get_nbd_volume_info,
    }

    pool_config = volume_config["meta"]["pool"]
    pool_type = pool_config["meta"]["type"]
    volume_info_getter = volume_info_getters[pool_type]

    return volume_info_getter(volume_config)


def get_qemu_virt_image_info(virt_image_config):
    info = collections.OrderedDict()
    info["file"] = collections.OrderedDict()

    volume_config = virt_image_config["spec"]["volume"]
    access_auth, volume_info = get_qemu_virt_image_volume_info(volume_config)
    info["file"].update(volume_info)
    info["driver"] = image_format = virt_image_config["spec"]["format"]

    encryption = collections.OrderedDict()
    encryption_config = virt_image_config["spec"].get("encryption")
    if encryption_config:
        encryption = {
            "type": encryption_config["type"],
            "id": encryption_config["name"],
            "format": encryption_config["format"],
            "data": encryption_config["data"],
            "file": encryption_config["file"],
        }
        if image_format == "luks":
            info["key-secret"] = encryption_config["name"]
        elif image_format == "qcow2" and encryption_config["format"] == "luks":
            info["encrypt.key-secret"] = encryption_config["name"]
            info["encrypt.format"] = encryption_config["encrypt"]["format"]

    # TODO: Add filters here

    return access_auth, encryption, info


def get_qemu_virt_image_object(object_opts):
    def _get_qemu_virt_image_tls_x509_object(auth):
        obj = "--object tls-creds-x509,id={name},endpoint=client,dir={dir}"
        opts = {"tls-creds": auth["name"]}
        return obj.format(**auth), opts

    def _get_qemu_virt_image_secret_object(encryption):
        obj = "--object secret,id={name},format={format}"

        if encryption["stored"] == "file":
            obj += ",file={file}"
            opts = {"password-secret": auth["name"]}
        else:
            # TODO: cookie-secret
            obj += ",data={data}"
            opts = {"key-secret": auth["name"]}

        # luks in qcow2
        encrypt = encryption["encrypt"]
        if encrypt:
            opts = {f"encrypt.{k}": v for k, v in opts.items()}
            opts.update({f"encrypt.{k}": v for k in encrypt if encrypt[k]})

        return obj.format(**encryption), opts

    mapping = {
        "secret": _get_qemu_virt_image_secret_object,
        "tls-creds-x509": _get_qemu_virt_image_tls_x509_object,
    }

    getter = mapping.get(object_opts["object-type"])
    return getter(object_opts) if getter else None, None


def get_qemu_virt_image_json(virt_image_opts):
    """Generate image json representation."""
    return "'json:%s'" % json.dumps(virt_image_opts)


def get_qemu_virt_image_opts(virt_image_opts):
    """Generate image-opts."""

    def _dict_to_dot(dct):
        """Convert dictionary to dot representation."""
        flat = []
        prefix = []
        stack = [dct.items()]
        while stack:
            it = stack[-1]
            try:
                key, value = next(it)
            except StopIteration:
                if prefix:
                    prefix.pop()
                stack.pop()
                continue
            if isinstance(value, collections.Mapping):
                prefix.append(key)
                stack.append(value.items())
            else:
                flat.append((".".join(prefix + [key]), value))
        return flat

    return ",".join(["%s=%s" % (attr, value) for attr, value in _dict_to_dot(virt_image_opts)])


def get_qemu_virt_image_repr(virt_image_config, output=None):
    def _parse_virt_image_options():
        options = [
            "preallocation", "cluster_size", "lazy_refcounts",
            "compat", "extent_size_hint", "compression_type",
        ]
        opts = {k: v for k in options if k in virt_image_spec and virt_image_spec[k]}

        # TODO: data_file, backing_file

        return opts

    virt_image_spec = virt_image_config["spec"]

    mapping = {
        "uri": lambda i: virt_image_spec["volume"]["spec"]["uri"],
        "json": get_qemu_virt_image_json,
        "opts": get_qemu_virt_image_opts,
    }

    auth, sec, info =  get_qemu_virt_image_info(virt_image_config)
    auth_repr, auth_opts = get_qemu_virt_image_object(auth) if auth else "", {}
    sec_repr, sec_opts = get_qemu_virt_image_object(sec) if sec else "", {}

    func = mapping.get(output)
    if func is None:
        func = mapping["json"] if auth or sec else mapping["uri"]
    image_repr = func(info)

    opts = _parse_virt_image_options()
    if auth_opts:
        opts.update(auth_opts)
    if sec_opts:
        opts.update(sec_opts)

    return auth_repr, sec_repr, opts, image_repr


def create(image_config, arguments):
    create_cmd = (
        "create {secret_object} {image_format} "
        "{backing_file} {backing_format} {unsafe!b} {options} "
        "{image_filename} {image_size}"
    )

    def _dd(image_tag):
        qemu_img_cmd = ""
        virt_image_config = image_spec["virt-images"][image_tag]
        volume_config = virt_image_config["spec"]["volume"]

        if virt_image_config["spec"]["format"] == "raw":
            count = utils_numeric.normalize_data_size(
                int(volume_config["spec"]["size"]),
                order_magnitude="M"
            )
            qemu_img_cmd = "dd if=/dev/zero of=%s count=%s bs=1M" % (
                volume_config["spec"]["path"],
                count,
                block_size,
            )
        else:
            raise

    def _qemu_img_create(virt_image_tag):
        qemu_img_cmd = ""
        virt_image_config = image_spec["virt-images"][virt_image_tag]
        virt_image_spec = virt_image_config["spec"]
        volume_config = virt_image_config["spec"]["volume"]

        cmd_dict = {}
        cmd_dict["image_format"] = virt_image_spec["format"]
        cmd_dict["secret_objects"] = secret_objects = list()

        base_tag = _get_base_image(virt_image_tag, image_meta["topology"])
        if base_tag is not None:
            base_virt_image_config = image_spec["virt-images"][base_tag]
            auth_repr, sec_repr, _, cmd_dict["backing_file"] = get_qemu_virt_image_repr(base_virt_image_config, image_repr_format)
            if auth_repr:
                secret_objects.append(auth_repr)
            if sec_repr:
                secret_objects.append(sec_repr)
            cmd_dict["backing_format"] = base_virt_image_config["spec"]["format"]

        auth_repr, sec_repr, options, image_uri = get_qemu_virt_image_repr(virt_image_config, "uri")
        if auth_repr:
            secret_objects.append(auth_repr)
        if sec_repr:
            secret_objects.append(sec_repr)

        cmd_dict["image_filename"] = image_uri
        cmd_dict["image_size"] = int(volume_config["spec"]["size"])
        if options:
            cmd_dict["options"] = ",".join(options)

        qemu_img_cmd = (
            qemu_image_binary
            + " "
            + cmd_formatter.format(create_cmd, **cmd_dict)
        )

        LOG.info("Create image by command: %s",  qemu_img_cmd)
        cmd_result = process.run(
            qemu_img_cmd, shell=True, verbose=False, ignore_status=True
        )

        if cmd_result.exit_status != 0:
            LOG.warning(
                "Failed to create image %s\n%s" % (virt_image_tag, cmd_result)
            )
        return cmd_result.exit_status



    qemu_image_binary = arguments.get("qemu_img_binary", QEMU_IMG_BINARY)
    image_repr_format = arguments.get("source_repr")
    image_meta = image_config["meta"]
    image_spec = image_config["spec"]

    virt_images = list(image_meta["topology"].values())[0]
    for tag in virt_images:
        _qemu_img_create(tag)


def destroy(image_config, arguments):
    LOG.debug("To destroy the qemu image %s" % image_config["meta"]["name"])


def snapshot(image_config, arguments):
    pass


def rebase(image_config, arguments):
    pass


def commit(image_config, arguments):
    pass


def convert(image_config, arguments):
    pass
