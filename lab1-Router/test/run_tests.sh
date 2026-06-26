#!/usr/bin/env bash
# lab1-router/test/run_tests.sh
#
# Guion de pruebas para ejecutar DENTRO de la CLI de Mininet (no es automatico:
# son los comandos que se escriben en mininet> para validar cada requisito).
#
# Levanta primero la topologia en otra terminal:
#   cd lab1-router && make run
#
# Luego, en la CLI de Mininet, ejecuta:
cat <<'EOF'
============================================================
 PRUEBAS LAB 1 - Router IPv4 estatico
============================================================

1) Conectividad entre todos los hosts (4 subredes distintas):
     mininet> pingall
   Esperado: 0% dropped (todos se alcanzan).

2) Decremento de TTL (captura con Scapy):
     mininet> h4 python3 test/recv_ttl.py &
     mininet> h1 ping -c 1 10.0.4.1
   Esperado en recv_ttl: TTL = 64 - (numero de routers).
   h1->h4 atraviesa s1,s2,s3 => TTL=61 en h4.
   Compara con h2->h4 (atraviesa s2,s3 => TTL=62) y h3->h4 (s3 => TTL=63).

3) Descarte por TTL agotado (+ ICMP Time Exceeded opcional):
     mininet> h1 python3 test/send_ttl.py --dst 10.0.4.1 --ttl 1 --gw-mac 00:00:00:01:01:00
   Esperado: el primer router descarta el paquete. Si ENABLE_ICMP_TIME_EXCEEDED
   esta activo en router.p4, se recibe "ICMP Time Exceeded desde 10.0.1.254".

4) Descarte por falta de ruta (default drop):
     mininet> h1 ping -c 2 10.0.99.99
   Esperado: 100% packet loss (no hay entrada LPM => default_action = drop).

5) Verificacion de reescritura de MAC (Wireshark/tcpdump):
     mininet> h4 tcpdump -e -n -i eth0 icmp &
     mininet> h1 ping -c 1 10.0.4.1
   Esperado: el frame que llega a h4 tiene src MAC = 00:00:00:03:02:00 (s3 port2)
   y dst MAC = 08:00:00:00:04:44 (h4), confirmando la reescritura por salto.
============================================================
EOF
