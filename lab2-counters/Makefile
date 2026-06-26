# lab2-counters/Makefile
# Compila counters.p4 al JSON que ejecuta BMv2 (simple_switch).

P4C       ?= p4c-bm2-ss
P4_SRC    := counters.p4
BUILD_DIR := build
JSON      := $(BUILD_DIR)/counters.json
P4INFO    := $(BUILD_DIR)/counters.p4info.txt

.PHONY: all clean run

all: $(JSON)

$(JSON): $(P4_SRC)
	mkdir -p $(BUILD_DIR)
	$(P4C) --target bmv2 --arch v1model \
		--p4runtime-files $(P4INFO) \
		-o $(JSON) $(P4_SRC)

run: all
	sudo python3 topology.py

clean:
	rm -rf $(BUILD_DIR)
	sudo mn -c 2>/dev/null || true
	rm -f *.pcap
