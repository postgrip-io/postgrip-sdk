# Unified SDK operation coverage

Contract bundle: `30423932a9a4b38254475d117d5e8d1cd19954266d3a7c58835cdde9a7fcb8a9`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 191 | 191 | 191 | 182 | 9 | 191 | 137 | 52 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 46 | 37 | 9 | 46 |
| Worker | 21 | 21 | 0 | 21 |
| Service | 124 | 124 | 0 | 124 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
