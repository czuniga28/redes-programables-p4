/* -*- P4_16 -*- */
/*
 * lab2-counters/counters.p4
 *
 * Sistema de contadores y estadisticas de trafico en el plano de datos P4
 * (arquitectura v1model / BMv2).
 *
 * Funcionalidades:
 *   - Direct counters por flujo (IP origen + IP destino): tabla flow_stats con
 *     un direct_counter que mide paquetes y bytes de cada flujo monitoreado.
 *   - Contadores globales por protocolo (TCP, UDP, ICMP, otros): array indirecto
 *     proto_counter de 4 celdas.
 *   - Registro del tamano de los paquetes con registers: flow_bytes acumula los
 *     bytes por flujo y last_pkt_size guarda el ultimo tamano observado.
 *   - Deteccion de flujo elefante: si los bytes acumulados de un flujo superan
 *     un umbral configurable (register elephant_threshold, fijado por el plano
 *     de control), se marca el flujo en el register flow_elephant.
 *
 * Reenvio: switch unico, hosts en la misma subred. La tabla ipv4_forward asigna
 * el puerto de salida por IP destino; el ARP estatico de los hosts ya coloca la
 * MAC destino correcta, por lo que no se reescribe la trama.
 */

#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4 = 0x0800;
const bit<8>  P_ICMP = 8w1;
const bit<8>  P_TCP  = 8w6;
const bit<8>  P_UDP  = 8w17;

/* Numero maximo de flujos monitoreables (indice de registers por flow_id). */
const bit<32> MAX_FLOWS = 256;

/*************************************************************************
*********************** H E A D E R S  ***********************************
*************************************************************************/

typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

header tcp_t {
    bit<16> srcPort;
    bit<16> dstPort;
    bit<32> seqNo;
    bit<32> ackNo;
    bit<4>  dataOffset;
    bit<3>  res;
    bit<9>  flags;
    bit<16> window;
    bit<16> checksum;
    bit<16> urgentPtr;
}

header udp_t {
    bit<16> srcPort;
    bit<16> dstPort;
    bit<16> length_;
    bit<16> checksum;
}

header icmp_t {
    bit<8>  type;
    bit<8>  code;
    bit<16> checksum;
    bit<32> rest;
}

struct metadata {
    bit<32> flow_id;     /* indice del flujo asignado por el plano de control */
    bit<1>  flow_known;  /* 1 si el flujo esta en flow_stats */
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
    tcp_t      tcp;
    udp_t      udp;
    icmp_t     icmp;
}

/*************************************************************************
*********************** P A R S E R  ***********************************
*************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        meta.flow_id = 0;
        meta.flow_known = 0;
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_IPV4: parse_ipv4;
            default:   accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol) {
            P_TCP:   parse_tcp;
            P_UDP:   parse_udp;
            P_ICMP:  parse_icmp;
            default: accept;
        }
    }

    state parse_tcp  { packet.extract(hdr.tcp);  transition accept; }
    state parse_udp  { packet.extract(hdr.udp);  transition accept; }
    state parse_icmp { packet.extract(hdr.icmp); transition accept; }
}

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

/*************************************************************************
**************  I N G R E S S   P R O C E S S I N G   ******************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    /* ---- Contadores globales por protocolo (indices 0=TCP,1=UDP,2=ICMP,3=otros) ---- */
    counter(4, CounterType.packets_and_bytes) proto_counter;

    /* ---- Direct counter por flujo (IP origen + IP destino) ---- */
    direct_counter(CounterType.packets_and_bytes) flow_counter;

    /* ---- Registers para tamano de paquetes y deteccion de elefantes ---- */
    register<bit<32>>(MAX_FLOWS) flow_bytes;     /* bytes acumulados por flujo */
    register<bit<32>>(MAX_FLOWS) flow_pkts;      /* paquetes acumulados por flujo */
    register<bit<1>>(MAX_FLOWS)  flow_elephant;  /* 1 si el flujo supero el umbral */
    register<bit<32>>(1)         elephant_threshold; /* umbral en bytes (control plane) */
    register<bit<32>>(1)         last_pkt_size;   /* ultimo tamano de paquete visto */

    action drop() {
        mark_to_drop(standard_metadata);
    }

    /* El plano de control asocia cada (srcIP,dstIP) con un flow_id estable
     * usado como indice de los registers. El direct_counter cuenta por entrada. */
    action count_flow(bit<32> flow_id) {
        meta.flow_id = flow_id;
        meta.flow_known = 1;
    }

    table flow_stats {
        key = {
            hdr.ipv4.srcAddr: exact;
            hdr.ipv4.dstAddr: exact;
        }
        actions = {
            count_flow;
            NoAction;
        }
        counters = flow_counter;       /* direct counter asociado a la tabla */
        size = MAX_FLOWS;
        default_action = NoAction();
    }

    /* Reenvio simple por IP destino (switch unico, misma subred). */
    action set_egress(bit<9> port) {
        standard_metadata.egress_spec = port;
    }

    table ipv4_forward {
        key = {
            hdr.ipv4.dstAddr: exact;
        }
        actions = {
            set_egress;
            drop;
        }
        size = 64;
        default_action = drop();
    }

    apply {
        if (hdr.ipv4.isValid()) {
            /* 1) Clasificacion y conteo global por protocolo. */
            bit<32> pidx;
            if (hdr.ipv4.protocol == P_TCP) {
                pidx = 0;
            } else if (hdr.ipv4.protocol == P_UDP) {
                pidx = 1;
            } else if (hdr.ipv4.protocol == P_ICMP) {
                pidx = 2;
            } else {
                pidx = 3;
            }
            proto_counter.count(pidx);

            /* 2) Direct counter por flujo (solo flujos instalados). */
            flow_stats.apply();

            /* 3) Registro de tamano + acumulado por flujo + deteccion elefante. */
            last_pkt_size.write(0, standard_metadata.packet_length);
            if (meta.flow_known == 1) {
                bit<32> b;
                flow_bytes.read(b, meta.flow_id);
                b = b + standard_metadata.packet_length;
                flow_bytes.write(meta.flow_id, b);

                bit<32> p;
                flow_pkts.read(p, meta.flow_id);
                flow_pkts.write(meta.flow_id, p + 1);

                bit<32> thr;
                elephant_threshold.read(thr, 0);
                if (thr != 0 && b > thr) {
                    flow_elephant.write(meta.flow_id, 1);
                }
            }

            /* 4) Reenvio. */
            ipv4_forward.apply();
        } else {
            drop();
        }
    }
}

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply { }
}

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {
        update_checksum(
            hdr.ipv4.isValid(),
            { hdr.ipv4.version, hdr.ipv4.ihl, hdr.ipv4.diffserv,
              hdr.ipv4.totalLen, hdr.ipv4.identification, hdr.ipv4.flags,
              hdr.ipv4.fragOffset, hdr.ipv4.ttl, hdr.ipv4.protocol,
              hdr.ipv4.srcAddr, hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.tcp);
        packet.emit(hdr.udp);
        packet.emit(hdr.icmp);
    }
}

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
