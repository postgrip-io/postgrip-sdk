# Unified SDK operation coverage

Contract bundle: `818e166aba4309c9b6a85896fb312bbb286e72c819f84b31cb3bf2e97202c916`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 195 | 195 | 195 | 186 | 9 | 195 | 138 | 55 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 46 | 37 | 9 | 46 |
| Worker | 21 | 21 | 0 | 21 |
| Service | 128 | 128 | 0 | 128 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
