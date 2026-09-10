from linux_why.core.graph import Inspector
from linux_why.inspectors import file, kernel_module, netif, package, process, socket, systemd

INSPECTORS: dict[str, Inspector] = {
    "package": package.inspect,
    "file": file.inspect,
    "process": process.inspect,
    "unit": systemd.inspect,
    "socket": socket.inspect,
    "interface": netif.inspect,
    "module": kernel_module.inspect,
}
