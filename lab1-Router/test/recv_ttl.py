#!/usr/bin/env python3
# lab1-router/test/recv_ttl.py
#
# Escucha en la interfaz del host e imprime el TTL de cada paquete IPv4
# recibido. Sirve para demostrar que el TTL decrementa un valor por cada
# router P4 atravesado.
#
# Uso (dentro del namespace del host destino, desde la CLI de Mininet):
#   mininet> h4 python3 test/recv_ttl.py &
#   mininet> h1 ping -c1 h4

import sys

from scapy.all import IP, ICMP, TCP, UDP, sniff


def handle(pkt):
    if IP not in pkt:
        return
    ip = pkt[IP]
    proto = "OTROS"
    if ICMP in pkt:
        proto = "ICMP"
    elif TCP in pkt:
        proto = "TCP"
    elif UDP in pkt:
        proto = "UDP"
    print("[RX] %-5s %s -> %s  TTL=%d  len=%d"
          % (proto, ip.src, ip.dst, ip.ttl, ip.len))
    sys.stdout.flush()


def main():
    iface = sys.argv[1] if len(sys.argv) > 1 else "eth0"
    print("*** Escuchando en %s (Ctrl-C para salir)" % iface)
    sniff(iface=iface, prn=handle, store=False)


if __name__ == "__main__":
    main()
