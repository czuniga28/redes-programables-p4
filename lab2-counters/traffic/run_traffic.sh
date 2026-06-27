#!/usr/bin/env bash
# lab2-counters/traffic/run_traffic.sh
#
# Comandos de referencia para generar trafico mixto y validar los contadores.
# Se escriben en la CLI de Mininet (mininet>). Tambien se muestra la variante
# con iperf como alternativa a Scapy.
cat <<'EOF'
============================================================
 GENERACION DE TRAFICO - LAB 2 (contadores)
============================================================

Prerrequisitos:
  Terminal A:  cd lab2-counters && make run        (levanta topologia)
  Terminal B:  cd lab2-counters && python3 controller.py   (estadisticas)

--- Opcion 1: Scapy (trafico controlado y reproducible) ---

  # Flujo TCP grande -> debe marcarse ELEFANTE (>100 KB):
  mininet> h1 python3 traffic/gen_traffic.py --dst 10.0.1.2 --proto tcp  --count 250 --size 1000

  # Flujo UDP mediano:
  mininet> h3 python3 traffic/gen_traffic.py --dst 10.0.1.4 --proto udp  --count 120 --size 500

  # Flujo ICMP pequeno:
  mininet> h1 python3 traffic/gen_traffic.py --dst 10.0.1.3 --proto icmp --count 40

  # Trafico de retorno:
  mininet> h2 python3 traffic/gen_traffic.py --dst 10.0.1.1 --proto udp  --count 60  --size 300

--- Opcion 2: iperf (carga real TCP/UDP) ---

  mininet> h2 iperf -s &                 # servidor en h2
  mininet> h1 iperf -c 10.0.1.2 -t 10    # cliente TCP h1->h2 (elefante)
  mininet> h4 iperf -s -u &              # servidor UDP en h4
  mininet> h3 iperf -c 10.0.1.4 -u -b 5M -t 8

Observa el controlador (Terminal B): los contadores por protocolo y por flujo
deben crecer en linea con el trafico inyectado, y el flujo TCP grande debe
pasar a estado ELEFANTE.
============================================================
EOF
