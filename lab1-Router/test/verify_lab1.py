#!/usr/bin/env python3
# lab1-router/test/verify_lab1.py
#
# Verificacion NO interactiva del Lab 1 (para CI / evidencia automatica).
# Reutiliza la topologia de topology.py, levanta la red, carga las tablas y
# ejecuta las pruebas obligatorias imprimiendo PASS/FAIL:
#   1) Conectividad total (pingall).
#   2) Decremento de TTL multi-salto (h1->h4 debe llegar con TTL=61).
#   3) Descarte por falta de ruta (default drop).
#   4) (Opcional) ICMP Time Exceeded al agotar el TTL.
#
# Uso (como root, con build/router.json ya compilado):
#   python3 test/verify_lab1.py
#
# Devuelve codigo de salida 0 si todas las pruebas obligatorias pasan.

import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from mininet.net import Mininet          # noqa: E402
from mininet.link import TCLink          # noqa: E402
from mininet.log import setLogLevel      # noqa: E402

import topology as topo                   # noqa: E402
from p4_mininet import P4Host, P4Switch   # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    mark = "PASS" if ok else "FAIL"
    print("[%s] %s %s" % (mark, name, ("- " + detail) if detail else ""))


def main():
    if not os.path.isfile(topo.JSON_PATH):
        sys.exit("ERROR: falta %s (ejecuta make)." % topo.JSON_PATH)

    net = Mininet(topo=topo.RouterTopo(), host=P4Host, switch=P4Switch,
                  link=TCLink, controller=None)
    net.start()
    topo.configure_hosts(net)
    topo.load_tables(net)

    h1, h2, h3, h4 = net.get("h1", "h2", "h3", "h4")

    # --- 1) Conectividad total ---
    loss = net.pingAll()
    check("Conectividad total (pingall)", loss == 0.0,
          "perdida=%.0f%%" % loss)

    # --- 2) Decremento de TTL (h1->h4 atraviesa s1,s2,s3 => TTL=61) ---
    out = h1.cmd("ping -c1 -W2 10.0.4.1")
    m = re.search(r"ttl=(\d+)", out)
    ttl = int(m.group(1)) if m else -1
    check("TTL decrementa 3 saltos (h1->h4)", ttl == 61,
          "ttl observado=%s (esperado 61)" % ttl)

    # Comparacion: h3->h4 atraviesa solo s3 => TTL=63
    out = h3.cmd("ping -c1 -W2 10.0.4.1")
    m = re.search(r"ttl=(\d+)", out)
    ttl2 = int(m.group(1)) if m else -1
    check("TTL un salto (h3->h4)", ttl2 == 63,
          "ttl observado=%s (esperado 63)" % ttl2)

    # --- 3) Descarte por falta de ruta (default drop) ---
    out = h1.cmd("ping -c2 -W1 10.0.99.99")
    m = re.search(r"(\d+)% packet loss", out)
    drop = int(m.group(1)) if m else -1
    check("Default drop sin ruta", drop == 100,
          "perdida=%s%% (esperado 100)" % drop)

    # --- 4) ICMP Time Exceeded (opcional) ---
    out = h1.cmd("python3 test/send_ttl.py --dst 10.0.4.1 --ttl 1 "
                 "--gw-mac 00:00:00:01:01:00")
    icmp_ok = "Time Exceeded" in out
    print("[%s] ICMP Time Exceeded (opcional) - %s"
          % ("PASS" if icmp_ok else "INFO",
             "recibido" if icmp_ok else "no recibido (feature opcional)"))

    net.stop()

    obligatorias = [ok for name, ok in results]
    total = len(obligatorias)
    passed = sum(obligatorias)
    print("\n=== RESULTADO LAB 1: %d/%d pruebas obligatorias PASS ==="
          % (passed, total))
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    setLogLevel("warning")
    main()
