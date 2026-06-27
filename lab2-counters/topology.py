#!/usr/bin/env python3
# lab2-counters/topology.py
#
# Topologia Mininet para el laboratorio de contadores/estadisticas.
#
#   h1 (10.0.1.1)   h2 (10.0.1.2)   h3 (10.0.1.3)   h4 (10.0.1.4)
#        \              |               |              /
#         \             |               |             /
#          +----------------- [s1: switch P4 BMv2] ----------+
#
# 1 switch P4 y 4 hosts en la misma subred (10.0.1.0/24) generando trafico mixto.
# El plano de control (controller.py) instala el reenvio, los flujos y el umbral.
#
# Uso:
#   sudo python3 topology.py          # deja una CLI de Mininet abierta
# En OTRA terminal:
#   python3 controller.py             # instala tablas y muestra estadisticas

import os
import sys

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.topo import Topo

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "utils"))
from p4_mininet import P4Host, P4Switch  # noqa: E402

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(THIS_DIR, "build", "counters.json")
THRIFT_PORT = 9090

# host -> (ip, mac). Todos en 10.0.1.0/24, puerto del switch = indice.
HOSTS = {
    "h1": ("10.0.1.1/24", "08:00:00:00:01:11"),
    "h2": ("10.0.1.2/24", "08:00:00:00:02:22"),
    "h3": ("10.0.1.3/24", "08:00:00:00:03:33"),
    "h4": ("10.0.1.4/24", "08:00:00:00:04:44"),
}


class CountersTopo(Topo):
    def build(self, **opts):
        s1 = self.addSwitch("s1", cls=P4Switch, sw_path="simple_switch",
                            json_path=JSON_PATH, thrift_port=THRIFT_PORT)
        for i, name in enumerate(HOSTS, start=1):
            h = self.addHost(name, cls=P4Host)
            self.addLink(h, s1, port1=0, port2=i)


def configure_hosts(net):
    """Asigna IP/MAC y siembra ARP estatico entre todos los hosts.

    El switch P4 no procesa ARP; con entradas estaticas las tramas ya llevan
    la MAC destino correcta y solo hace falta elegir el puerto de salida.
    """
    for name, (ip, mac) in HOSTS.items():
        h = net.get(name)
        h.setMAC(mac, h.defaultIntf())
        h.setIP(ip.split("/")[0], int(ip.split("/")[1]))

    for name, (ip, mac) in HOSTS.items():
        h = net.get(name)
        for other, (oip, omac) in HOSTS.items():
            if other == name:
                continue
            h.cmd("arp -s %s %s" % (oip.split("/")[0], omac))


def main():
    if not os.path.isfile(JSON_PATH):
        print("ERROR: no existe %s. Ejecuta 'make' primero." % JSON_PATH)
        sys.exit(1)

    topo = CountersTopo()
    net = Mininet(topo=topo, host=P4Host, switch=P4Switch,
                  link=TCLink, controller=None)
    net.start()
    configure_hosts(net)

    print("\n*** Switch P4 arriba en thrift %d." % THRIFT_PORT)
    print("*** En otra terminal: python3 controller.py")
    print("*** Genera trafico, p.ej.: h1 python3 traffic/gen_traffic.py\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    main()
