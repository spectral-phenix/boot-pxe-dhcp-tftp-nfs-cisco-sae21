"""Vérifie le comportement du serveur DHCP/TFTP dans le laboratoire de lab.sh.

Chaque test se place dans le namespace d'une machine cliente, prend son adresse
MAC, puis fait un vrai échange DHCP (Discover → Offer → Request → ACK) avec
Scapy, à travers le relais du routeur quand le client est dans Réseau3.

Usage (root, après « lab/lab.sh up ») :
    pip install scapy
    sudo python3 lab/test_lab.py
"""
import os
import random
import subprocess
import sys
import tempfile
import time

ICI = os.path.abspath(__file__)

TESTS = [
    # (nom, namespace, MAC, attendu)  attendu = None si aucune adresse ne doit être donnée
    ("VM clipxe-4 (Réseau2)", "r2", "bc:24:11:f4:f2:52",
     {"ip": "172.16.4.54", "routeur": "172.16.4.49", "next_server": "172.16.4.49", "fichier": "pxelinux.0"}),
    ("Raspberry raspi-4 (Réseau3, via relais)", "r3", "d8:3a:dd:0c:fe:70",
     {"ip": "172.16.4.10", "routeur": "172.16.4.1", "next_server": "172.16.4.57",
      "opt66": "172.16.4.57", "opt60": "PXEClient", "opt43": "Raspberry Pi Boot"}),
    ("PC pcsalletp-4 (Réseau3, via relais)", "r3", "f0:b2:b9:23:30:d7",
     {"ip": "172.16.4.11", "routeur": "172.16.4.1", "next_server": "172.16.4.57", "fichier": "pxelinux.0"}),
    ("Machine inconnue dans Réseau3", "r3", "02:00:00:00:00:99", None),
    ("Machine inconnue dans Réseau2", "r2", "02:00:00:00:00:98", None),
]
BAIL_ATTENDU = 1800


def dans_ns(ns, *args, **kw):
    return subprocess.run(["ip", "netns", "exec", ns, *args], capture_output=True, text=True, **kw)


# ---------------------------------------------------------------------------
# Partie exécutée DANS le namespace du client : un échange DHCP complet
# ---------------------------------------------------------------------------
def client_dhcp(mac):
    from scapy.all import BOOTP, DHCP, IP, UDP, AsyncSniffer, Ether, conf, sendp
    conf.checkIPaddr = False
    conf.verb = 0
    brut = bytes.fromhex(mac.replace(":", ""))
    xid = random.randint(1, 2**31)

    def echange(type_msg, extra=()):
        paquet = (Ether(src=mac, dst="ff:ff:ff:ff:ff:ff") / IP(src="0.0.0.0", dst="255.255.255.255")
                  / UDP(sport=68, dport=67)
                  / BOOTP(chaddr=brut, xid=xid, flags=0x8000)
                  / DHCP(options=[("message-type", type_msg), *extra,
                                  ("vendor_class_id", b"PXEClient"), "end"]))
        ecoute = AsyncSniffer(iface="eth0", count=1,
                              lfilter=lambda p: p.haslayer(BOOTP) and p[BOOTP].xid == xid and p[BOOTP].op == 2)
        ecoute.start()
        time.sleep(0.2)
        sendp(paquet, iface="eth0")
        ecoute.join(timeout=3)
        if ecoute.running:
            ecoute.stop()
        return ecoute.results[0] if ecoute.results else None

    offre = echange("discover")
    if offre is None:
        print("AUCUNE_OFFRE")
        return
    ip = offre[BOOTP].yiaddr
    serveur = dict(o for o in offre[DHCP].options if isinstance(o, tuple)).get("server_id")
    ack = echange("request", [("requested_addr", ip), ("server_id", serveur)])
    if ack is None:
        print("PAS_D_ACK")
        return
    opts = {o[0]: o[1] for o in ack[DHCP].options if isinstance(o, tuple)}
    dec = lambda v: v.decode(errors="replace") if isinstance(v, bytes) else str(v)
    res = {
        "type": dec(opts.get("message-type")),
        "ip": ack[BOOTP].yiaddr,
        "routeur": dec(opts.get("router")),
        "bail": dec(opts.get("lease_time")),
        "next_server": ack[BOOTP].siaddr,
        "fichier": ack[BOOTP].file.rstrip(b"\0").decode(),
        "opt66": dec(opts.get("tftp_server_name", "")),
        "opt60": dec(opts.get("vendor_class_id", "")),
        "opt43": dec(opts.get("vendor_specific", "")),
    }
    print("RESULTAT", repr(res))


# ---------------------------------------------------------------------------
# Partie pilote
# ---------------------------------------------------------------------------
def main():
    resultats = []
    for nom, ns, mac, attendu in TESTS:
        dans_ns(ns, "ip", "link", "set", "eth0", "address", mac)
        sortie = dans_ns(ns, sys.executable, ICI, "--client", mac).stdout
        obtenu = None
        for ligne in sortie.splitlines():
            if ligne.startswith("RESULTAT "):
                obtenu = eval(ligne[9:])  # dictionnaire produit par client_dhcp()
        if attendu is None:
            resultats.append((nom, "aucune adresse (deny unknown-clients)",
                              "aucune" if obtenu is None else obtenu["ip"], obtenu is None))
            continue
        if obtenu is None:
            resultats.append((nom, attendu["ip"], "aucune réponse", False))
            continue
        ecarts = [f"{k}={obtenu.get(k)!r}" for k, v in attendu.items() if obtenu.get(k) != v]
        if obtenu["bail"] != str(BAIL_ATTENDU):
            ecarts.append(f"bail={obtenu['bail']} s")
        detail = f"{obtenu['ip']}, bail {obtenu['bail']} s, fichier {obtenu['fichier']!r}"
        if obtenu["opt43"]:
            detail += f", options 60/66/43 = {obtenu['opt60']} / {obtenu['opt66']} / {obtenu['opt43']}"
        resultats.append((nom, attendu["ip"], detail + ("" if not ecarts else "  ⚠ " + ", ".join(ecarts)),
                          not ecarts))

    # Le Raspberry, une fois son adresse obtenue, joint le serveur à travers le routeur
    dans_ns("r3", "ip", "link", "set", "eth0", "address", "d8:3a:dd:0c:fe:70")
    dans_ns("r3", "ip", "addr", "add", "172.16.4.10/27", "dev", "eth0")
    dans_ns("r3", "ip", "route", "add", "default", "via", "172.16.4.1")
    ping = dans_ns("r3", "ping", "-c", "2", "-W", "1", "172.16.4.57").stdout
    ttl = "ttl=63" in ping
    resultats.append(("Ping raspi → servpxe à travers le routeur", "réponse, TTL 63 (1 routeur)",
                      "TTL 63" if ttl else "échec", ttl))

    with tempfile.TemporaryDirectory() as d:
        cible = os.path.join(d, "cmdline.txt")
        dans_ns("r3", "tftp", "172.16.4.57", "-c", "get", "94162035/cmdline.txt", cible)
        ok = os.path.exists(cible) and "nfsroot=172.16.4.57:/srv/nfs/94162035" in open(cible).read()
        resultats.append(("TFTP : le Raspberry télécharge son cmdline.txt", "fichier reçu",
                          "fichier reçu" if ok else "échec", ok))
    dans_ns("r3", "ip", "addr", "flush", "dev", "eth0")

    largeur = max(len(r[0]) for r in resultats)
    for nom, attendu, obtenu, ok in resultats:
        print(f"{'OK   ' if ok else 'ÉCHEC'} {nom:<{largeur}}  attendu : {attendu}\n      {'':<{largeur}}  obtenu  : {obtenu}")
    echecs = sum(not r[3] for r in resultats)
    print(f"\n{len(resultats) - echecs}/{len(resultats)} tests réussis")
    sys.exit(1 if echecs else 0)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--client":
        client_dhcp(sys.argv[2])
    else:
        main()
