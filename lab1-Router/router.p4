/* -*- P4_16 -*- */
/*
 * lab1-router/router.p4
 *
 * Router IPv4 estatico implementado sobre la arquitectura v1model (BMv2).
 *
 * Funcionalidades:
 *   - Parsing de Ethernet e IPv4.
 *   - Reenvio basado en Longest Prefix Match (tabla ipv4_lpm) configurada
 *     estaticamente desde el plano de control via thrift.
 *   - Decremento de TTL en cada salto; descarte si TTL llega a 0.
 *   - Reescritura de MAC origen (la del puerto de salida del router) y MAC
 *     destino (la del siguiente salto).
 *   - Descarte por defecto cuando no existe ruta (default drop).
 *   - [OPCIONAL +10%] Generacion de ICMP Time Exceeded (tipo 11, codigo 0)
 *     cuando un paquete se descarta por TTL agotado. Se puede desactivar
 *     comentando la macro ENABLE_ICMP_TIME_EXCEEDED.
 */

#include <core.p4>
#include <v1model.p4>

/* Habilita el envio de ICMP Time Exceeded al expirar el TTL.
 * Comentar esta linea para dejar solo el comportamiento obligatorio (drop). */
#define ENABLE_ICMP_TIME_EXCEEDED

const bit<16> TYPE_IPV4 = 0x0800;
const bit<8>  PROTO_ICMP = 8w1;
const bit<8>  ICMP_TIME_EXCEEDED = 8w11;

/*************************************************************************
*********************** H E A D E R S  ***********************************
*************************************************************************/

typedef bit<9>  egressSpec_t;
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

/* Cabecera ICMP usada solo para construir la respuesta Time Exceeded. */
header icmp_t {
    bit<8>  type;
    bit<8>  code;
    bit<16> checksum;
    bit<32> unused;
}

/* Copia interna del paquete original que se incrusta dentro del ICMP. */
header ipv4_t_inner {
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

/* Primeros 8 bytes del payload original (RFC 792 exige incluirlos). */
header payload8_t {
    bit<64> data;
}

struct metadata {
    /* vacio: este router no necesita metadata persistente */
}

struct headers {
    ethernet_t   ethernet;
    ipv4_t       ipv4;
    icmp_t       icmp;
    ipv4_t_inner ipv4_inner;
    payload8_t   payload8;
}

/*************************************************************************
*********************** P A R S E R  ***********************************
*************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
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
        /* Extraemos 8 bytes del payload por si hay que generar ICMP Time
         * Exceeded. Solo lo intentamos cuando el header IPv4 no tiene opciones
         * (ihl == 5) para mantener el offset alineado. */
        transition select(hdr.ipv4.ihl) {
            4w5:     parse_payload8;
            default: accept;
        }
    }

    state parse_payload8 {
        packet.extract(hdr.payload8);
        transition accept;
    }
}

/*************************************************************************
************   C H E C K S U M    V E R I F I C A T I O N   *************
*************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

/*************************************************************************
**************  I N G R E S S   P R O C E S S I N G   ******************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    /* Descarta el paquete (marca el puerto de salida como invalido). */
    action drop() {
        mark_to_drop(standard_metadata);
    }

    /* Reenvio normal: fija siguiente salto y puerto de salida.
     * - dstAddr: MAC del siguiente salto (se escribe ahora).
     * - port:    puerto fisico de salida.
     * La MAC origen se fija en egress segun el puerto de salida. */
    action ipv4_forward(macAddr_t dstAddr, egressSpec_t port) {
        standard_metadata.egress_spec = port;
        hdr.ethernet.dstAddr = dstAddr;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }

    /* Tabla de enrutamiento por Longest Prefix Match.
     * Se llena estaticamente desde el plano de control (sX-commands.txt). */
    table ipv4_lpm {
        key = {
            hdr.ipv4.dstAddr: lpm;
        }
        actions = {
            ipv4_forward;
            drop;
            NoAction;
        }
        size = 1024;
        default_action = drop();   /* sin ruta => descarte por defecto */
    }

#ifdef ENABLE_ICMP_TIME_EXCEEDED
    /* Construye una respuesta ICMP Time Exceeded reusando el paquete actual:
     * el IPv4 original se convierte en el bloque incrustado y se antepone un
     * nuevo IPv4 + ICMP. El paquete se reenvia por el puerto de entrada. */
    action send_icmp_time_exceeded(macAddr_t src_mac, ip4Addr_t src_ip) {
        /* 1) Copiar IPv4 original al header interno (data de retorno). */
        hdr.ipv4_inner.setValid();
        hdr.ipv4_inner.version        = hdr.ipv4.version;
        hdr.ipv4_inner.ihl            = hdr.ipv4.ihl;
        hdr.ipv4_inner.diffserv       = hdr.ipv4.diffserv;
        hdr.ipv4_inner.totalLen       = hdr.ipv4.totalLen;
        hdr.ipv4_inner.identification = hdr.ipv4.identification;
        hdr.ipv4_inner.flags          = hdr.ipv4.flags;
        hdr.ipv4_inner.fragOffset     = hdr.ipv4.fragOffset;
        hdr.ipv4_inner.ttl            = hdr.ipv4.ttl;
        hdr.ipv4_inner.protocol       = hdr.ipv4.protocol;
        hdr.ipv4_inner.hdrChecksum    = hdr.ipv4.hdrChecksum;
        hdr.ipv4_inner.srcAddr        = hdr.ipv4.srcAddr;
        hdr.ipv4_inner.dstAddr        = hdr.ipv4.dstAddr;

        /* 2) Cabecera ICMP Time Exceeded. */
        hdr.icmp.setValid();
        hdr.icmp.type     = ICMP_TIME_EXCEEDED;
        hdr.icmp.code     = 8w0;
        hdr.icmp.checksum = 16w0;   /* recalculado en MyComputeChecksum */
        hdr.icmp.unused   = 32w0;

        /* 3) Nuevo IPv4 externo: del router (src_ip) hacia el emisor original. */
        bit<32> orig_src = hdr.ipv4.srcAddr;
        hdr.ipv4.version    = 4w4;
        hdr.ipv4.ihl        = 4w5;
        hdr.ipv4.diffserv   = 8w0;
        /* 20 (IP ext) + 8 (ICMP) + 20 (IP interno) + 8 (payload) = 56 bytes. */
        hdr.ipv4.totalLen   = 16w56;
        hdr.ipv4.flags      = 3w0;
        hdr.ipv4.fragOffset = 13w0;
        hdr.ipv4.ttl        = 8w64;
        hdr.ipv4.protocol   = PROTO_ICMP;
        hdr.ipv4.hdrChecksum = 16w0;
        hdr.ipv4.srcAddr    = src_ip;
        hdr.ipv4.dstAddr    = orig_src;

        /* 4) Ethernet: regresar por el puerto de entrada. */
        hdr.ethernet.dstAddr = hdr.ethernet.srcAddr;
        hdr.ethernet.srcAddr = src_mac;
        standard_metadata.egress_spec = standard_metadata.ingress_port;

        /* 5) Truncar a 70 bytes: 14 (eth) + 56 (IP+ICMP+IP+8). */
        truncate((bit<32>)70);
    }

    /* Asocia el puerto de ingreso con la IP/MAC de esa interfaz del router,
     * usadas como origen del ICMP. Se llena desde el plano de control. */
    table icmp_responder {
        key = {
            standard_metadata.ingress_port: exact;
        }
        actions = {
            send_icmp_time_exceeded;
            drop;
        }
        size = 64;
        default_action = drop();
    }
#endif

    apply {
        if (hdr.ipv4.isValid()) {
            if (hdr.ipv4.ttl <= 1) {
                /* TTL agotado: descartar. Opcionalmente responder ICMP. */
#ifdef ENABLE_ICMP_TIME_EXCEEDED
                icmp_responder.apply();
#else
                drop();
#endif
            } else {
                ipv4_lpm.apply();
            }
        }
    }
}

/*************************************************************************
****************  E G R E S S   P R O C E S S I N G   *****************
*************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {

    /* Fija la MAC origen segun el puerto fisico de salida (MAC de la
     * interfaz del router). Se llena desde el plano de control. */
    action set_smac(macAddr_t smac) {
        hdr.ethernet.srcAddr = smac;
    }

    table smac_rewrite {
        key = {
            standard_metadata.egress_port: exact;
        }
        actions = {
            set_smac;
            NoAction;
        }
        size = 64;
        default_action = NoAction();
    }

    apply {
        /* Solo reescribimos MAC origen para trafico reenviado normal.
         * El ICMP Time Exceeded ya fijo su propia MAC origen en ingress. */
        if (hdr.ipv4.isValid()) {
            smac_rewrite.apply();
        }
    }
}

/*************************************************************************
*************   C H E C K S U M    C O M P U T A T I O N   **************
*************************************************************************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {
        /* Recalcular checksum IPv4 (cambia por TTL y por ICMP). */
        update_checksum(
            hdr.ipv4.isValid(),
            { hdr.ipv4.version,
              hdr.ipv4.ihl,
              hdr.ipv4.diffserv,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);

        /* Checksum ICMP sobre ICMP + IP interno + 8 bytes de payload. */
        update_checksum(
            hdr.icmp.isValid(),
            { hdr.icmp.type,
              hdr.icmp.code,
              hdr.icmp.unused,
              hdr.ipv4_inner.version,
              hdr.ipv4_inner.ihl,
              hdr.ipv4_inner.diffserv,
              hdr.ipv4_inner.totalLen,
              hdr.ipv4_inner.identification,
              hdr.ipv4_inner.flags,
              hdr.ipv4_inner.fragOffset,
              hdr.ipv4_inner.ttl,
              hdr.ipv4_inner.protocol,
              hdr.ipv4_inner.hdrChecksum,
              hdr.ipv4_inner.srcAddr,
              hdr.ipv4_inner.dstAddr,
              hdr.payload8.data },
            hdr.icmp.checksum,
            HashAlgorithm.csum16);
    }
}

/*************************************************************************
***********************  D E P A R S E R  *******************************
*************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        /* Estos solo son validos en la respuesta ICMP Time Exceeded. */
        packet.emit(hdr.icmp);
        packet.emit(hdr.ipv4_inner);
        packet.emit(hdr.payload8);
    }
}

/*************************************************************************
***********************  S W I T C H  ***********************************
*************************************************************************/

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
