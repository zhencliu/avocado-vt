from . import qemu_image_handlers


_qemu_image_handlers = {
    "create": qemu_image_handlers.create,
    "destroy": qemu_image_handlers.destroy,
}


def get_qemu_image_handler(cmd):
    return _qemu_image_handlers.get(cmd)


__all__ = ["get_qemu_image_handler"]
