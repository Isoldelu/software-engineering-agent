# Network OS Release Note

## Release 1213

Included software packages:

- openssl 3.0.8
- ethtool 5.15

openssl is used for secure communication in network devices. ethtool is used for Ethernet interface inspection and configuration.

## Release 1214

Added software packages:

- nginx 1.24
- tcpdump 4.99

nginx is used to simulate a lightweight management-plane web service. tcpdump is used for packet capture and network traffic analysis.

Compatibility note:

- nginx 1.24 depends on openssl.
- tcpdump requires libpcap.so.
