# Retour d'expérience

*SAÉ 21 — Construire un réseau informatique pour une petite structure — groupe 4 (Emirkan Ö., Mohamed H., Elvin T.)*

## 1. Introduction

La SAÉ 21 nous a amenés à concevoir et déployer une infrastructure réseau complète en trois jours. L'objectif était de mettre en place un démarrage par le réseau (PXE) permettant d'installer des systèmes d'exploitation sur trois types de machines : des machines virtuelles hébergées sur un serveur Proxmox, un Raspberry Pi 4 (architecture ARM) et un PC de salle de TP (architecture x86).

L'infrastructure reposait sur une chaîne de services interdépendants : un plan d'adressage VLSM sur la classe 172.16.4.0/26, un serveur DHCP avec relais, un serveur TFTP, des partages NFS, et une configuration SSH et VLAN sur les équipements Cisco. Le projet nous a confrontés à des problèmes réels d'administration réseau, sur du matériel physique et avec de fortes contraintes de temps.

## 2. Organisation et déroulement

Dès le premier jalon, nous avons établi un plan d'adressage VLSM et un diagramme de Gantt pour structurer les trois jours. La répartition des tâches visait le travail en parallèle : pendant qu'un membre configurait les équipements Cisco (routeur et switch), les deux autres travaillaient sur les services Linux du serveur PXE.

Le premier jour a été le plus dense, avec la majorité des jalons de configuration. Le deuxième était consacré aux services NFS et TFTP et au démarrage des machines clientes. La rédaction du rapport s'est étalée sur les trois jours, chacun contribuant au fur et à mesure.

## 3. Difficultés rencontrées et résolutions

### Filtrage du DHCP par le portail captif

La difficulté la plus longue et la plus inattendue. Le PC de la salle envoyait correctement ses DHCP Discover, le routeur les relayait vers le serveur (confirmé par le `debug` Cisco), mais rien n'arrivait côté serveur, même avec un `tcpdump` sur toutes les interfaces.

Après avoir vérifié la configuration du relais, les droits du serveur, les règles `iptables` et même changé de routeur, nous avons identifié que le portail captif filtrait les paquets UDP à destination du port 67 entrant sur ens19. Modifier la configuration du portail pour autoriser ce trafic a immédiatement résolu le problème.

### Compatibilité SSH entre Cisco et OpenSSH

La connexion SSH du serveur Linux vers les équipements Cisco échouait sur des erreurs de négociation d'algorithmes : les versions récentes d'OpenSSH désactivent par défaut les algorithmes anciens utilisés par le Cisco 2901. L'ajout des directives `KexAlgorithms` et `Ciphers` dans `/etc/ssh/ssh_config`, et la génération de la clé RSA dans le bon ordre (hostname → domain-name → `crypto key generate rsa` → `ip ssh version 2`), ont réglé le problème.

### Erreurs de syntaxe DHCP et NFS

isc-dhcp-server exige une déclaration `subnet` pour chaque interface sur laquelle il écoute, même s'il n'y distribue aucune adresse. Sans celle de Réseau1, toutes les requêtes relayées étaient rejetées sans aucun message dans les journaux, ce qui rendait le diagnostic très difficile.

## 4. Ce que nous avons appris

Sur le plan technique, la SAÉ nous a donné une vision concrète d'une infrastructure réseau professionnelle. Nous comprenons chaque maillon de la chaîne PXE et ses points de défaillance. Nous avons progressé en administration Linux (systemd, interfaces réseau, NFS, DHCP) et en configuration Cisco IOS (VLAN, port-security, DHCP snooping, SSH).

Sur le plan méthodologique, savoir diagnostiquer vaut autant que maîtriser les commandes. Lire un `syslog`, interpréter une capture Wireshark, utiliser `tcpdump` avec les bons filtres ou le `debug` Cisco nous a permis de résoudre des problèmes que la documentation seule n'aurait pas suffi à identifier.

Le travail en parallèle a aussi été un apprentissage : découper les tâches en tenant compte des dépendances entre jalons nous a fait avancer bien plus vite qu'en séquentiel.

## 5. Conclusion

La SAÉ 21 a été l'une des plus formatrices de notre cursus, par la richesse des sujets techniques et par la réalité des problèmes rencontrés. Contrairement aux TP classiques, aucune panne n'avait de solution évidente dans la documentation : chacune nous a obligés à analyser, diagnostiquer et raisonner méthodiquement.
