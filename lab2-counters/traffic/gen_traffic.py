#!/usr/bin/env python3
# lab2-counters/traffic/gen_traffic.py
#
# Genera trafico mixto controlado con Scapy para validar los contadores P4.
# Pensado para ejecutarse dentro del namespace de un host de Mininet.
#
# Ejemplos (desde la CLI de Mininet):
#   mininet> h1 python3 traffic/gen_traffic.py --dst 10.0.1.2 --proto tcp  --count 200 --size 1000
#   mininet> h3 python3 traffic/gen_traffic.py --dst 10.0.1.4 --proto udp  --count 100 --size 500
#   mininet> h1 python3 traffic/gen_traffic.py --dst 10.0.1.3 --proto icmp --count 50
#
# Un flujo TCP grande (--proto tcp --count 200 --size 1000 ~ 200 KB) deberia
# cruzar el umbral de elefante por defecto (100 KB) y aparecer marcado en el
# controlador.

import argparse

from scapy.all import IP, TCP, UDP, ICMP, Raw, send


def build_packet(dst, proto, size):
    payload = Raw(load=b"X" * max(0, size))
    ip = IP(dst=dst)
    if proto == "tcp":
        l4 = TCP(dport=5001, sport=40000, flags="PA")
    elif proto == "udp":
        l4 = UDP(dport=5001, sport=40000)
    else:
        l4 = ICMP()
    return ip / l4 / payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", required=True, help="IP destino")
    ap.add_argument("--proto", choices=["tcp", "udp", "icmp"], default="tcp")
    ap.add_argument("--count", type=int, default=100, help="numero de paquetes")
    ap.add_argument("--size", type=int, default=800, help="bytes de payload")
    ap.add_argument("--inter", type=float, default=0.01, help="seg entre paquetes")
    args = ap.parse_args()

    # Enviamos en capa 3 (send): el kernel resuelve la MAC destino usando la
    # tabla ARP estatica de la topologia. Evitamos scapy.getmacbyip(), que hace
    # su propio ARP y se cuelga porque el switch P4 de contadores descarta ARP.
    pkt = build_packet(args.dst, args.proto, args.size)
    total = (len(pkt) + 14) * args.count  # +14 por la cabecera Ethernet en cable
    print("*** Enviando %d paquetes %s a %s (~%d bytes c/u en cable, ~%d totales)"
          % (args.count, args.proto.upper(), args.dst, len(pkt) + 14, total))
    send(pkt, count=args.count, inter=args.inter, verbose=False)
    print("*** Listo.")


if __name__ == "__main__":
    main()
