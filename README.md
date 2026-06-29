# Redes Programables con P4 — Investigación y Laboratorio Base

Router IPv4 estático + Contadores y estadísticas de tráfico, implementados en
**P4** sobre **BMv2** y **Mininet**.

**Fecha de entrega:** 29 de junio de 2026
**Autores:** Christopher Zúñiga · Adrian Hernandez

---

## Estructura del repositorio

```
.
├── lab1-router/          # Lab 1: Router IPv4 estático
│   ├── router.p4         #   programa P4 (parser, LPM, TTL, MAC rewrite, ICMP)
│   ├── topology.py       #   topología Mininet: 3 routers P4 + 4 hosts
│   ├── s1/s2/s3-commands.txt  # tablas estáticas (plano de control thrift)
│   ├── Makefile          #   compila router.p4 -> build/router.json
│   └── test/             #   scripts Scapy (TTL) y guion de pruebas
├── lab2-counters/        # Lab 2: Contadores y estadísticas
│   ├── counters.p4       #   direct counters, contadores por protocolo, registers
│   ├── topology.py       #   topología Mininet: 1 switch P4 + 4 hosts
│   ├── controller.py     #   plano de control Python (thrift): instala y lee
│   ├── Makefile          #   compila counters.p4 -> build/counters.json
│   └── traffic/          #   generadores de tráfico (Scapy / iperf)
├── utils/
│   └── p4_mininet.py     # clases Mininet P4Host / P4Switch (compartidas)
├── informe/
│   └── informe.pdf       # informe de investigación (Parte I)
├── video.mp4         
│    └── link.txt          # link al video demostrativo
└── README.md
```

## Requisitos del entorno

Probado sobre el entorno estándar del **P4 Tutorial** (Ubuntu + p4lang).
Herramientas necesarias en el `PATH`:

- `p4c` (concretamente `p4c-bm2-ss`) — compilador P4.
- `simple_switch` y `simple_switch_CLI` — BMv2 (behavioral-model).
- `mininet` (`mn`) — emulador de red.
- `python3` con `scapy`.
- Opcional: `iperf`, `wireshark`/`tcpdump`.

> La forma más rápida de tener todo es la VM/contenedor del
> [p4lang/tutorials](https://github.com/p4lang/tutorials), que ya incluye
> p4c, BMv2, Mininet y Scapy.

### Entorno reproducible con Docker (alternativa)

Si no quieres instalar el toolchain a mano, en `docker/Dockerfile` hay una
imagen lista (Ubuntu 22.04 + p4c + BMv2 + Mininet + Scapy). Ambos laboratorios
fueron compilados y **verificados end-to-end** en este entorno.

```bash
# Construir la imagen (en Apple Silicon se emula amd64)
docker build --platform=linux/amd64 -t p4lab docker/

# Abrir una shell con el repo montado (privilegiado: Mininet usa namespaces/veth)
docker run --rm -it --privileged --platform=linux/amd64 \
    -v "$PWD":/work -w /work p4lab bash
```

Dentro del contenedor se usan exactamente los mismos comandos `make` / `python3`
descritos abajo.

### Verificación automática (no interactiva)

Cada laboratorio incluye un script de verificación headless que levanta la red,
inyecta tráfico y comprueba los requisitos sin la CLI interactiva de Mininet:

```bash
# Lab 1  -> 4/4 pruebas obligatorias (+ ICMP Time Exceeded opcional)
cd lab1-router && make && python3 test/verify_lab1.py

# Lab 2  -> 5/5 pruebas (contadores por protocolo/flujo + flujo elefante)
cd lab2-counters && make && python3 test/verify_lab2.py
```

La salida completa de una corrida real está en `docs/evidence/`.

---

## Lab 1 — Router IPv4 estático

Topología (3 routers P4, 4 subredes):

```
 h1 10.0.1.1            h3 10.0.3.1   h4 10.0.4.1
     \                       |           /
   [s1] --10.0.12.0/24-- [s2] --10.0.23.0/24-- [s3]
                             |
                        h2 10.0.2.1
```

### Ejecutar

```bash
cd lab1-router
make            # compila router.p4 -> build/router.json
make run        # = sudo python3 topology.py (carga las tablas automáticamente)
```

### Pruebas (en la CLI de Mininet)

```text
mininet> pingall                      # conectividad entre las 4 subredes
mininet> h4 python3 test/recv_ttl.py &
mininet> h1 ping -c1 10.0.4.1         # TTL llega a 61 (3 routers)
mininet> h1 python3 test/send_ttl.py --dst 10.0.4.1 --ttl 1   # TTL agotado -> ICMP Time Exceeded
mininet> h1 ping -c2 10.0.99.99       # sin ruta -> default drop (100% loss)
```

El guion completo está en `lab1-router/test/run_tests.sh`.

**Funcionalidades cubiertas:** parsing Ethernet/IPv4, LPM desde el plano de
control, decremento de TTL y descarte en TTL=0, reescritura de MAC origen/destino
por salto, descarte por defecto sin ruta, y (opcional) ICMP Time Exceeded.

---

## Lab 2 — Contadores y estadísticas de tráfico

Topología: 1 switch P4 + 4 hosts en `10.0.1.0/24`.

### Ejecutar (dos terminales)

```bash
# Terminal A — topología
cd lab2-counters
make            # compila counters.p4 -> build/counters.json
make run        # sudo python3 topology.py

# Terminal B — plano de control + estadísticas (refresco cada 2 s)
cd lab2-counters
python3 controller.py
```

### Generar tráfico (en la CLI de Mininet, Terminal A)

```text
mininet> h1 python3 traffic/gen_traffic.py --dst 10.0.1.2 --proto tcp  --count 250 --size 1000  # elefante
mininet> h3 python3 traffic/gen_traffic.py --dst 10.0.1.4 --proto udp  --count 120 --size 500
mininet> h1 python3 traffic/gen_traffic.py --dst 10.0.1.3 --proto icmp --count 40
```

Más ejemplos (incluyendo iperf) en `lab2-counters/traffic/run_traffic.sh`.

**Funcionalidades cubiertas:** direct counters por flujo (IP origen + IP destino),
contadores globales por protocolo (TCP/UDP/ICMP/otros), registro del tamaño de
paquetes con *registers*, lectura periódica desde Python (thrift) con salida
formateada cada ≤5 s, y detección de flujo elefante por umbral configurable
(`--threshold`).

---

## Parte I — Informe de investigación

En `informe/informe.pdf` (fuente LaTeX en `informe/informe.tex`). Cubre la
evolución del plano de datos, el lenguaje P4 y PISA, P4Runtime y el control
plane, y casos de uso (INT, load balancing, seguridad, producción), con
referencias en formato IEEE.

Para recompilar el PDF:

```bash
cd informe && pdflatex informe.tex && pdflatex informe.tex
```
