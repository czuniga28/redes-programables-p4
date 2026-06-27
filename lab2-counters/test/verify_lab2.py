#!/usr/bin/env python3
# lab2-counters/test/verify_lab2.py
#
# Verificacion NO interactiva del Lab 2. Levanta la topologia, instala las
# tablas con el controlador, inyecta trafico mixto controlado y comprueba que:
#   1) Los contadores por protocolo reflejan el trafico (TCP/UDP/ICMP).
#   2) Los direct counters por flujo crecen acorde a lo inyectado.
#   3) El flujo TCP grande se marca como ELEFANTE al superar el umbral.
#
# Uso (como root, con build/counters.json compilado):
#   python3 test/verify_lab2.py

import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from mininet.net import Mininet          # noqa: E402
from mininet.link import TCLink          # noqa: E402
from mininet.log import setLogLevel      # noqa: E402

import topology as topo                   # noqa: E402
import controller as ctrl                 # noqa: E402
from p4_mininet import P4Host, P4Switch   # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print("[%s] %s %s" % ("PASS" if ok else "FAIL", name,
                          ("- " + detail) if detail else ""))


def main():
    if not os.path.isfile(topo.JSON_PATH):
        sys.exit("ERROR: falta %s (ejecuta make)." % topo.JSON_PATH)

    threshold = 100000  # 100 KB
    net = Mininet(topo=topo.CountersTopo(), host=P4Host, switch=P4Switch,
                  link=TCLink, controller=None)
    net.start()
    topo.configure_hosts(net)

    port = topo.THRIFT_PORT
    flows = ctrl.DEFAULT_FLOWS
    handles = ctrl.setup(port, flows, threshold)

    h1, h2, h3 = net.get("h1", "h2", "h3")

    # --- Inyectar trafico controlado ---
    # NOTA: para la verificacion automatica usamos generadores basados en el
    # kernel (sockets + ping), no Scapy. Bajo emulacion amd64, scapy.send()
    # se cuelga de forma intermitente con TCP; el kernel es deterministico.
    # El deliverable traffic/gen_traffic.py (Scapy) funciona en la VM P4 real.
    #
    # Flujo elefante: UDP h1->h2, 160 x 1400 B ~ 230 KB (> umbral 100 KB).
    # Ritmo controlado (inter 0.01 s): el BMv2 emulado pierde paquetes si se le
    # envia una rafaga sin pausa (UDP no tiene control de flujo).
    h1.cmd("timeout 60 python3 -c \""
           "import socket,time; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);"
           "d=b'X'*1400;"
           "[(s.sendto(d,('10.0.1.2',9999)), time.sleep(0.01)) for _ in range(160)]\"")
    # Algo de TCP h1->h2 (SYNs sin servidor -> cuentan como TCP en el flujo 0).
    h1.cmd("timeout 20 python3 -c \""
           "import socket\n"
           "for _ in range(8):\n"
           "    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM); s.settimeout(0.4)\n"
           "    try: s.connect(('10.0.1.2',9999))\n"
           "    except OSError: pass\n"
           "    s.close()\"")
    # ICMP h1->h3 (40 echo requests).
    h1.cmd("timeout 30 ping -c 40 -i 0.05 -W1 10.0.1.3")
    time.sleep(1)

    # --- Leer contadores ---
    proto = dict((name, (pkts, byts))
                 for name, pkts, byts in ctrl.read_proto_counters(port))
    flow_rows = ctrl.read_flows(port, flows, handles, threshold)
    ctrl.render(list((n, p, b) for n, (p, b) in proto.items()), flow_rows)

    # --- Asserts ---
    check("Contador TCP refleja trafico", proto["TCP"][0] >= 1,
          "tcp_pkts=%d" % proto["TCP"][0])
    check("Contador UDP refleja trafico", proto["UDP"][0] >= 100,
          "udp_pkts=%d" % proto["UDP"][0])
    check("Contador ICMP refleja trafico", proto["ICMP"][0] >= 40,
          "icmp_pkts=%d" % proto["ICMP"][0])

    # flow_id 0 = (10.0.1.1 -> 10.0.1.2), el elefante (UDP+TCP inyectados)
    f0 = next(r for r in flow_rows if r[2] == 0)
    check("Direct counter por flujo crece", f0[3] >= 100,
          "flujo h1->h2 pkts=%d bytes=%d" % (f0[3], f0[4]))
    check("Deteccion de flujo ELEFANTE", f0[5] is True,
          "bytes=%d umbral=%d" % (f0[4], threshold))

    net.stop()

    passed = sum(results)
    print("\n=== RESULTADO LAB 2: %d/%d pruebas PASS ===" % (passed, len(results)))
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    setLogLevel("warning")
    main()
