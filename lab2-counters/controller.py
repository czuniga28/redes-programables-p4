#!/usr/bin/env python3
# lab2-counters/controller.py
#
# Plano de control del laboratorio de contadores. Usa el API thrift de BMv2
# (a traves de simple_switch_CLI) para:
#   1) Instalar el reenvio por IP destino (tabla ipv4_forward).
#   2) Registrar los flujos a monitorear (tabla flow_stats con direct_counter).
#   3) Fijar el umbral de flujo elefante (register elephant_threshold).
#   4) Leer periodicamente y mostrar en consola:
#        - contadores globales por protocolo (TCP/UDP/ICMP/otros),
#        - bytes/paquetes por flujo (direct counter),
#        - marca de flujo elefante.
#
# Uso:
#   python3 controller.py                       # setup + monitoreo cada 2 s
#   python3 controller.py --interval 5
#   python3 controller.py --threshold 200000    # umbral elefante en bytes
#   python3 controller.py --setup-only          # solo instala tablas y sale
#
# Requiere que la topologia (topology.py) este corriendo y exponiendo thrift.

import argparse
import re
import subprocess
import sys
import time

CLI_BIN = "simple_switch_CLI"

PROTO_NAMES = ["TCP", "UDP", "ICMP", "OTROS"]

# Reenvio por defecto: IP destino -> puerto del switch.
DEFAULT_FORWARD = {
    "10.0.1.1": 1,
    "10.0.1.2": 2,
    "10.0.1.3": 3,
    "10.0.1.4": 4,
}

# Flujos monitoreados por defecto: (src, dst) -> flow_id (indice estable).
DEFAULT_FLOWS = [
    ("10.0.1.1", "10.0.1.2", 0),
    ("10.0.1.3", "10.0.1.4", 1),
    ("10.0.1.1", "10.0.1.3", 2),
    ("10.0.1.2", "10.0.1.1", 3),
]


def run_cli(commands, thrift_port):
    """Ejecuta una lista de comandos en simple_switch_CLI y devuelve la salida."""
    payload = "\n".join(commands) + "\n"
    try:
        proc = subprocess.run(
            [CLI_BIN, "--thrift-port", str(thrift_port)],
            input=payload, capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        sys.exit("ERROR: no se encontro '%s' en el PATH." % CLI_BIN)
    except subprocess.TimeoutExpired:
        return ""
    return proc.stdout + proc.stderr


def parse_counter(text, label):
    """Extrae (bytes, packets) de la salida de counter_read para un label.

    BMv2 imprime, p.ej.:  flow_counter[0]= (16456 bytes, 32 packets)
    (el numero va ANTES de la palabra). Aceptamos tambien la forma bytes=NN.
    """
    for line in text.splitlines():
        if label not in line:
            continue
        b = re.search(r"(\d+)\s*bytes", line) or re.search(r"bytes\s*[:=]\s*(\d+)", line)
        p = re.search(r"(\d+)\s*packets", line) or re.search(r"packets\s*[:=]\s*(\d+)", line)
        if b and p:
            return int(b.group(1)), int(p.group(1))
    return 0, 0


def parse_register(text):
    """Extrae el ultimo entero de una salida de register_read."""
    nums = re.findall(r"(\d+)", text.split("=")[-1]) if "=" in text else []
    if nums:
        return int(nums[-1])
    nums = re.findall(r"(\d+)", text)
    return int(nums[-1]) if nums else 0


def setup(thrift_port, flows, threshold):
    """Instala reenvio, flujos y umbral. Devuelve dict flow_id -> entry_handle."""
    cmds = []
    for ip, port in DEFAULT_FORWARD.items():
        cmds.append("table_add ipv4_forward set_egress %s => %d" % (ip, port))
    out = run_cli(cmds, thrift_port)

    handles = {}
    for src, dst, fid in flows:
        out = run_cli(
            ["table_add flow_stats count_flow %s %s => %d" % (src, dst, fid)],
            thrift_port)
        m = re.search(r"handle\s+(\d+)", out)
        handles[fid] = int(m.group(1)) if m else fid

    # Umbral de elefante (bytes). register_write <nombre> <indice> <valor>.
    run_cli(["register_write elephant_threshold 0 %d" % threshold], thrift_port)

    print("*** Reenvio instalado: %s" % DEFAULT_FORWARD)
    print("*** Flujos monitoreados (src,dst -> flow_id -> handle):")
    for src, dst, fid in flows:
        print("      %-10s -> %-10s  flow_id=%d  handle=%d"
              % (src, dst, fid, handles[fid]))
    print("*** Umbral de flujo elefante: %d bytes\n" % threshold)
    return handles


def read_proto_counters(thrift_port):
    cmds = ["counter_read proto_counter %d" % i for i in range(4)]
    out = run_cli(cmds, thrift_port)
    result = []
    for i in range(4):
        b, p = parse_counter(out, "proto_counter[%d]" % i)
        result.append((PROTO_NAMES[i], p, b))
    return result


def read_flows(thrift_port, flows, handles, threshold):
    rows = []
    for src, dst, fid in flows:
        h = handles[fid]
        out = run_cli(["counter_read flow_counter %d" % h], thrift_port)
        b, p = parse_counter(out, "flow_counter")
        ele_out = run_cli(["register_read flow_elephant %d" % fid], thrift_port)
        is_ele = parse_register(ele_out) == 1 or b > threshold
        rows.append((src, dst, fid, p, b, is_ele))
    return rows


def render(proto_rows, flow_rows):
    ts = time.strftime("%H:%M:%S")
    print("=" * 64)
    print(" ESTADISTICAS DE TRAFICO P4    [%s]" % ts)
    print("=" * 64)
    print(" Contadores globales por protocolo")
    print(" %-8s %12s %14s" % ("PROTO", "PAQUETES", "BYTES"))
    print(" " + "-" * 36)
    for name, pkts, byts in proto_rows:
        print(" %-8s %12d %14d" % (name, pkts, byts))
    print()
    print(" Flujos monitoreados (direct counters)")
    print(" %-12s %-12s %9s %12s   %s" %
          ("SRC", "DST", "PAQUETES", "BYTES", "ESTADO"))
    print(" " + "-" * 58)
    for src, dst, fid, pkts, byts, is_ele in flow_rows:
        estado = "ELEFANTE" if is_ele else "ok"
        print(" %-12s %-12s %9d %12d   %s" %
              (src, dst, pkts, byts, estado))
    print("=" * 64 + "\n")


def main():
    ap = argparse.ArgumentParser(description="Controlador de contadores P4 (thrift).")
    ap.add_argument("--thrift-port", type=int, default=9090)
    ap.add_argument("--interval", type=float, default=2.0,
                    help="segundos entre lecturas (<=5 por requisito)")
    ap.add_argument("--threshold", type=int, default=100000,
                    help="umbral de flujo elefante en bytes")
    ap.add_argument("--setup-only", action="store_true",
                    help="solo instala tablas/umbral y termina")
    args = ap.parse_args()

    flows = DEFAULT_FLOWS
    handles = setup(args.thrift_port, flows, args.threshold)
    if args.setup_only:
        return

    print("*** Monitoreando cada %.1f s. Ctrl-C para salir.\n" % args.interval)
    try:
        while True:
            proto_rows = read_proto_counters(args.thrift_port)
            flow_rows = read_flows(args.thrift_port, flows, handles, args.threshold)
            render(proto_rows, flow_rows)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n*** Detenido por el usuario.")


if __name__ == "__main__":
    main()
