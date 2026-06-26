#!/usr/bin/env python3
# lab1-router/topology.py
#
# Topologia Mininet para el router IPv4 estatico en P4.
#
#   h1 (10.0.1.1)            h3 (10.0.3.1)   h4 (10.0.4.1)
#       \                        |             /
#        \                       |            /
#   [s1] --- 10.0.12.0/24 --- [s2] --- 10.0.23.0/24 --- [s3]
#        \                       |
#         \                      |
#          h?                   h2 (10.0.2.1)
#
# Resumen de puertos:
#   s1: 1->h1, 2->s2
#   s2: 1->h2, 2->s1, 3->s3
#   s3: 1->h3, 2->h4, 3->s2
#
# 3 routers P4 (s1,s2,s3) y 4 hosts en 4 subredes distintas.
#
# Uso:
#   sudo python3 topology.py
# Requiere haber compilado antes router.p4 -> build/router.json (make).

import os
import sys

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.topo import Topo

# Importar las clases auxiliares P4 desde ../utils
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "utils"))
from p4_mininet import P4Host, P4Switch  # noqa: E402

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(THIS_DIR, "build", "router.json")

# Definicion declarativa de hosts: nombre -> (ip, mac, gateway, gw_mac)
HOSTS = {
    "h1": dict(ip="10.0.1.1/24", mac="08:00:00:00:01:11",
               gw="10.0.1.254", gw_mac="00:00:00:01:01:00"),
    "h2": dict(ip="10.0.2.1/24", mac="08:00:00:00:02:22",
               gw="10.0.2.254", gw_mac="00:00:00:02:01:00"),
    "h3": dict(ip="10.0.3.1/24", mac="08:00:00:00:03:33",
               gw="10.0.3.254", gw_mac="00:00:00:03:01:00"),
    "h4": dict(ip="10.0.4.1/24", mac="08:00:00:00:04:44",
               gw="10.0.4.254", gw_mac="00:00:00:03:02:00"),
}

# Puerto thrift por switch (para el plano de control)
THRIFT = {"s1": 9090, "s2": 9091, "s3": 9092}


class RouterTopo(Topo):
    def build(self, **opts):
        # --- Switches P4 ---
        s1 = self.addSwitch("s1", cls=P4Switch, sw_path="simple_switch",
                            json_path=JSON_PATH, thrift_port=THRIFT["s1"])
        s2 = self.addSwitch("s2", cls=P4Switch, sw_path="simple_switch",
                            json_path=JSON_PATH, thrift_port=THRIFT["s2"])
        s3 = self.addSwitch("s3", cls=P4Switch, sw_path="simple_switch",
                            json_path=JSON_PATH, thrift_port=THRIFT["s3"])

        # --- Hosts (la IP/MAC se aplica luego en configure_hosts) ---
        h1 = self.addHost("h1", cls=P4Host)
        h2 = self.addHost("h2", cls=P4Host)
        h3 = self.addHost("h3", cls=P4Host)
        h4 = self.addHost("h4", cls=P4Host)

        # --- Enlaces host-switch (port number explicito) ---
        self.addLink(h1, s1, port1=0, port2=1)
        self.addLink(h2, s2, port1=0, port2=1)
        self.addLink(h3, s3, port1=0, port2=1)
        self.addLink(h4, s3, port1=0, port2=2)

        # --- Enlaces switch-switch ---
        self.addLink(s1, s2, port1=2, port2=2)   # 10.0.12.0/24
        self.addLink(s2, s3, port1=3, port2=3)   # 10.0.23.0/24


def configure_hosts(net):
    """IP, MAC, ruta por defecto y ARP estatico (BMv2 no hace ARP)."""
    for name, cfg in HOSTS.items():
        h = net.get(name)
        h.setMAC(cfg["mac"], h.defaultIntf())
        h.setIP(cfg["ip"].split("/")[0], int(cfg["ip"].split("/")[1]))
        h.cmd("ip route add default via %s" % cfg["gw"])
        # ARP estatico hacia el gateway -> MAC de la interfaz del router.
        h.cmd("arp -s %s %s" % (cfg["gw"], cfg["gw_mac"]))


def load_tables(net):
    """Carga sX-commands.txt en cada switch via simple_switch_CLI."""
    for sw, port in THRIFT.items():
        cmds = os.path.join(THIS_DIR, "%s-commands.txt" % sw)
        print("*** Cargando %s en %s (thrift %d)" % (cmds, sw, port))
        os.system("simple_switch_CLI --thrift-port %d < %s" % (port, cmds))


def main():
    if not os.path.isfile(JSON_PATH):
        print("ERROR: no existe %s. Ejecuta 'make' primero." % JSON_PATH)
        sys.exit(1)

    topo = RouterTopo()
    net = Mininet(topo=topo, host=P4Host, switch=P4Switch,
                  link=TCLink, controller=None)
    net.start()

    configure_hosts(net)
    load_tables(net)

    print("\n*** Red lista. Prueba: pingall, h1 ping h4, etc.")
    print("*** TTL: 'h1 traceroute h4' o usa scripts en test/\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    main()
