#!/usr/bin/env bash
# Reproduit la topologie de la SAÉ 21 sur une seule machine Linux, avec des
# « network namespaces » (une pile réseau isolée par équipement) reliés par
# des câbles virtuels (veth). Permet de tester dhcpd.conf, le relais DHCP,
# le routage et TFTP sans le matériel de la salle.
#
#   servpxe-4 ──ens19── Réseau1 /30 ──gi01── router-4 ──gi00── Réseau3 /27 ── r3 (Raspberry / PC)
#       └──ens20── Réseau2 /29 ── r2 (VM clipxe)
#
# Usage (root) : sudo lab/lab.sh up [dhcpd.conf]   |   sudo lab/lab.sh down
# Paquets : isc-dhcp-server isc-dhcp-relay tftpd-hpa iproute2
set -euo pipefail

RACINE="$(cd "$(dirname "$0")/.." && pwd)"
ETAT=/tmp/sae21-lab
NS=(servpxe router r2 r3)

down() {
    for ns in "${NS[@]}"; do ip netns pids "$ns" 2>/dev/null | xargs -r kill 2>/dev/null || true; done
    sleep 0.3
    for ns in "${NS[@]}"; do ip netns del "$ns" 2>/dev/null || true; done
    rm -rf "$ETAT"
}

up() {
    local conf="${1:-$RACINE/configs/serveur/dhcpd.conf}"
    down
    mkdir -p "$ETAT/srv/tftp/94162035"
    for ns in "${NS[@]}"; do ip netns add "$ns"; ip -n "$ns" link set lo up; done

    # Câblage : chaque paire veth est un câble entre deux équipements
    ip link add ens19 netns servpxe type veth peer name gi01 netns router   # Réseau1
    ip link add ens20 netns servpxe type veth peer name eth0 netns r2       # Réseau2
    ip link add gi00  netns router  type veth peer name eth0 netns r3       # Réseau3

    # servpxe-4 : configuration de configs/serveur/interfaces
    ip -n servpxe addr add 172.16.4.57/30 dev ens19
    ip -n servpxe addr add 172.16.4.49/29 dev ens20
    ip -n servpxe link set ens19 up
    ip -n servpxe link set ens20 up
    ip -n servpxe route add 172.16.4.0/27 via 172.16.4.58      # route statique vers Réseau3

    # router-4 : configuration de configs/cisco/router-4.txt
    ip -n router addr add 172.16.4.58/30 dev gi01
    ip -n router addr add 172.16.4.1/27  dev gi00
    ip -n router link set gi01 up
    ip -n router link set gi00 up
    ip netns exec router sysctl -qw net.ipv4.ip_forward=1
    # équivalent Linux de « ip helper-address 172.16.4.57 » sur Gi0/0
    ip netns exec router dhcrelay -4 -q -pf "$ETAT/relay.pid" -id gi00 -iu gi01 172.16.4.57

    ip -n r2 link set eth0 up
    ip -n r3 link set eth0 up

    # Serveur DHCP avec le fichier à tester, sur ens19 et ens20 uniquement
    touch "$ETAT/dhcpd.leases"
    ip netns exec servpxe dhcpd -4 -q -cf "$conf" -lf "$ETAT/dhcpd.leases" -pf "$ETAT/dhcpd.pid" ens19 ens20

    # Serveur TFTP (options de configs/serveur/tftpd-hpa), avec des fichiers factices
    echo "fichier de démarrage factice" > "$ETAT/srv/tftp/pxelinux.0"
    cp "$RACINE/configs/raspberry/cmdline.txt" "$ETAT/srv/tftp/94162035/cmdline.txt"
    # (-4 : les namespaces de test n'ont pas d'IPv6 ; l'utilisateur tftp est créé par le paquet tftpd-hpa)
    ip netns exec servpxe in.tftpd -4 --listen --address :69 --secure --user tftp \
        --pidfile "$ETAT/tftpd.pid" "$ETAT/srv/tftp"

    echo "Laboratoire prêt (dhcpd.conf : $conf)"
}

case "${1:-}" in
    up)   up "${2:-}" ;;
    down) down; echo "Laboratoire supprimé" ;;
    *)    echo "usage : $0 up [dhcpd.conf] | down"; exit 1 ;;
esac
