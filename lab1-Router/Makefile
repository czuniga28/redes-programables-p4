# lab1-router/Makefile
# Compila router.p4 al JSON que ejecuta BMv2 (simple_switch).

P4C       ?= p4c-bm2-ss
P4_SRC    := router.p4
BUILD_DIR := build
JSON      := $(BUILD_DIR)/router.json
P4INFO    := $(BUILD_DIR)/router.p4info.txt

.PHONY: all clean run

all: $(JSON)

$(JSON): $(P4_SRC)
	mkdir -p $(BUILD_DIR)
	$(P4C) --target bmv2 --arch v1model \
		--p4runtime-files $(P4INFO) \
		-o $(JSON) $(P4_SRC)

# Compila (si hace falta) y lanza la topologia. Requiere sudo (Mininet).
run: all
	sudo /home/p4/src/p4dev-python-venv/bin/python3 topology.py

clean:
	rm -rf $(BUILD_DIR)
	sudo mn -c 2>/dev/null || true
	rm -f *.pcap
