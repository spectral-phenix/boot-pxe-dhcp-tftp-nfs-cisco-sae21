# Ajouter un deuxième Raspberry Pi (jalon 12)

Procédure pour faire démarrer un second Raspberry Pi par le réseau, à côté du premier. Exemple : `raspi2-4`, numéro de série `93214211`, 12ᵉ adresse de Réseau3.

## 1. Relever son numéro de série et son adresse MAC

Sur le Pi, avec une carte SD le temps de la manipulation :

```bash
cat /proc/cpuinfo | grep Serial      # garder les 8 derniers caractères
ip addr show eth0 | grep ether       # adresse MAC
```

Activer aussi le démarrage réseau : `sudo raspi-config` → *Advanced Options* → *Boot Order* → *Network Boot*.

## 2. Réservation DHCP

Dans `/etc/dhcp/dhcpd.conf` (le bloc est déjà présent en commentaire dans [`configs/serveur/dhcpd.conf`](../configs/serveur/dhcpd.conf)) :

```conf
host raspi2-4 {
    hardware ethernet XX:XX:XX:XX:XX:XX;     # MAC relevée à l'étape 1
    fixed-address 172.16.4.12;
    next-server 172.16.4.57;
    option tftp-server-name "172.16.4.57";
    option vendor-class-identifier "PXEClient";
    option vendor-encapsulated-options "Raspberry Pi Boot";
}
```

```bash
systemctl restart isc-dhcp-server
```

Indispensable : avec `deny unknown-clients`, un Pi non déclaré n'obtient aucune adresse.

## 3. Fichiers de démarrage et racine

Le Pi cherche ses fichiers dans un dossier qui porte **son** numéro de série : on part d'une copie du premier.

```bash
PI_SERIAL2=93214211
mkdir -p /srv/tftp/$PI_SERIAL2 /srv/nfs/$PI_SERIAL2
cp -ar /srv/tftp/94162035/* /srv/tftp/$PI_SERIAL2/
cp -ar /srv/nfs/94162035/*  /srv/nfs/$PI_SERIAL2/
```

## 4. `cmdline.txt`

Remplacer le contenu de `/srv/tftp/93214211/cmdline.txt` par **une seule ligne** (voir [`cmdline-raspi2.txt`](../configs/raspberry/cmdline-raspi2.txt)) :

```
console=serial0,115200 console=tty1 root=/dev/nfs nfsroot=172.16.4.57:/srv/nfs/93214211,vers=3 proto=tcp rw ip=dhcp rootwait elevator=deadline
```

Sans ce changement, les deux Pi monteraient la même racine NFS et s'écraseraient mutuellement leurs fichiers.

## 5. Partage NFS

```bash
echo '/srv/nfs/93214211 *(rw,sync,no_subtree_check,no_root_squash)' >> /etc/exports
exportfs -ra
exportfs        # vérifier
```

## 6. Port du switch

Fa0/3 était éteint et dans le VLAN 10 :

```
switch-4(config)# interface FastEthernet0/3
switch-4(config-if)# switchport mode access
switch-4(config-if)# switchport access vlan 10
switch-4(config-if)# no shutdown
switch-4(config-if)# end
switch-4# write memory
```

## 7. Vérifier

```bash
tail -f /var/log/syslog | grep -E 'dhcp|tftp|nfs'
```

On doit voir le DHCPDISCOVER relayé, l'attribution de 172.16.4.12, puis les téléchargements TFTP depuis `/srv/tftp/93214211/`.
