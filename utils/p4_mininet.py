# utils/p4_mininet.py
#
# Clases auxiliares de Mininet para correr switches BMv2 (simple_switch) y
# hosts adaptados a P4. Reutilizadas por las topologias de lab1 y lab2.
#
# Basado en el helper del repo oficial p4lang/tutorials, simplificado y
# documentado para este laboratorio.

import os
import socket
import tempfile
from time import sleep

from mininet.log import debug, error, info
from mininet.moduledeps import pathCheck
from mininet.node import Host, Switch

SWITCH_START_TIMEOUT = 10  # segundos a esperar a que el switch abra su puerto thrift


class P4Host(Host):
    """Host de Mininet con offloading de NIC desactivado.

    Desactivar rx/tx/sg offload evita que la NIC virtual recalcule checksums o
    segmente paquetes, lo que distorsionaria las capturas (TTL, tamanos) y la
    contabilidad de bytes en el switch P4.
    """

    def config(self, **params):
        r = super(P4Host, self).config(**params)

        self.defaultIntf().rename("eth0")
        for off in ["rx", "tx", "sg"]:
            cmd = "/sbin/ethtool --offload eth0 %s off" % off
            self.cmd(cmd)

        # TCP reno para que iperf produzca curvas reproducibles.
        self.cmd("sysctl -w net.ipv4.tcp_congestion_control=reno")
        # Evitar que el host responda con ICMP unreachable propio durante drops.
        self.cmd("iptables -I OUTPUT -p icmp --icmp-type destination-unreachable -j DROP")
        return r

    def describe(self):
        print("**********")
        print("%s: IP=%s MAC=%s" % (
            self.name, self.defaultIntf().IP(), self.defaultIntf().MAC()))
        print("**********")


class P4Switch(Switch):
    """Switch Mininet que arranca un proceso BMv2 simple_switch.

    Cada switch expone un puerto thrift propio para que el plano de control
    (simple_switch_CLI / controlador Python) instale entradas y lea contadores.
    """

    device_id = 0

    def __init__(self, name, sw_path="simple_switch", json_path=None,
                 thrift_port=None, pcap_dump=False, log_console=False,
                 log_file=None, device_id=None, enable_debugger=False,
                 **kwargs):
        Switch.__init__(self, name, **kwargs)
        assert sw_path
        assert json_path
        # Verificar que el binario de BMv2 esta en el PATH.
        pathCheck(sw_path)
        # El JSON compilado por p4c debe existir.
        if not os.path.isfile(json_path):
            error("Invalid JSON file: %s\n" % json_path)
            exit(1)
        self.sw_path = sw_path
        self.json_path = json_path
        self.verbose = False
        self.thrift_port = thrift_port
        self.pcap_dump = pcap_dump
        self.enable_debugger = enable_debugger
        self.log_console = log_console
        self.log_file = log_file if log_file is not None else "/tmp/p4s.%s.log" % self.name
        if device_id is not None:
            self.device_id = device_id
            P4Switch.device_id = max(P4Switch.device_id, device_id)
        else:
            self.device_id = P4Switch.device_id
            P4Switch.device_id += 1
        self.nanomsg = "ipc:///tmp/bm-%d-log.ipc" % self.device_id

    @classmethod
    def setup(cls):
        pass

    def check_switch_started(self, pid):
        """Espera a que el switch abra el puerto thrift; aborta si murio."""
        for _ in range(SWITCH_START_TIMEOUT * 2):
            if not os.path.exists(os.path.join("/proc", str(pid))):
                return False
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("localhost", self.thrift_port))
            sock.close()
            if result == 0:
                return True
            sleep(0.5)
        return False

    def start(self, controllers):
        info("Starting P4 switch %s.\n" % self.name)
        args = [self.sw_path]
        for port, intf in list(self.intfs.items()):
            if not intf.IP():
                args.extend(["-i", str(port) + "@" + intf.name])
        if self.pcap_dump:
            args.append("--pcap")
        if self.thrift_port:
            args.extend(["--thrift-port", str(self.thrift_port)])
        if self.nanomsg:
            args.extend(["--nanolog", self.nanomsg])
        args.extend(["--device-id", str(self.device_id)])
        P4Switch.device_id += 1
        args.append(self.json_path)
        if self.enable_debugger:
            args.append("--debugger")
        if self.log_console:
            args.append("--log-console")
        logfile = self.log_file
        info(" ".join(args) + "\n")

        pid = None
        with tempfile.NamedTemporaryFile() as f:
            self.cmd(" ".join(args) + " >" + logfile + " 2>&1 & echo $! >> " + f.name)
            pid = int(f.read())
        debug("P4 switch %s PID is %d.\n" % (self.name, pid))
        if not self.check_switch_started(pid):
            error("P4 switch %s did not start correctly.\n" % self.name)
            exit(1)
        info("P4 switch %s has been started.\n" % self.name)

    def stop(self):
        self.cmd("kill %" + self.sw_path)
        self.cmd("wait")
        self.deleteIntfs()

    def attach(self, intf):
        assert 0, "Attach not implemented"

    def detach(self, intf):
        assert 0, "Detach not implemented"
