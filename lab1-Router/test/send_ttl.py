#!/usr/bin/env python3
# lab1-router/test/send_ttl.py
#
# Inyecta paquetes IPv4 con TTL configurable para demostrar:
#   1) Decremento de TTL por cada router (--ttl alto, observar en recv_ttl.py).
#   2) Descarte por TTL agotado y, opcionalmente, la respuesta ICMP Time
#      Exceeded (--ttl 1).
#
# Uso (dentro del namespace del host origen, desde la CLI de Mininet):
#   mininet> h1 python3 test/send_ttl.py --dst 10.0.4.1 --ttl 64
#   mininet> h1 python3 test/send_ttl.py --dst 10.0.4.1 --ttl 1   # fuerza expiracion

import argparse

from scapy.all import IP, ICMP, Ether, srp1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", required=True, help="IP destino")
    ap.add_argument("--ttl", type=int, default=64, help="TTL inicial")
    ap.add_argument("--iface", default="eth0")
    ap.add_argument("--gw-mac", default="00:00:00:01:01:00",
                    help="MAC del gateway (router) al que sale el paquete")
    args = ap.parse_args()

    pkt = (Ether(dst=args.gw_mac) /
           IP(dst=args.dst, ttl=args.ttl) /
           ICMP())
    print("*** Enviando ICMP echo a %s con TTL=%d" % (args.dst, args.ttl))
    resp = srp1(pkt, iface=args.iface, timeout=3, verbose=False)
    if resp is None:
        print("*** Sin respuesta (paquete descartado, p.ej. TTL agotado sin ICMP).")
        return
    ip = resp[IP]
    if ICMP in resp and resp[ICMP].type == 11:
        print("*** Recibido ICMP Time Exceeded desde %s (router que descarto)." % ip.src)
    elif ICMP in resp and resp[ICMP].type == 0:
        print("*** Recibido ICMP echo-reply desde %s con TTL=%d." % (ip.src, ip.ttl))
    else:
        print("*** Respuesta IP desde %s, TTL=%d, proto=%d."
              % (ip.src, ip.ttl, ip.proto))


if __name__ == "__main__":
    main()
