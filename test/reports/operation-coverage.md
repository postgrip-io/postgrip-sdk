# Unified SDK operation coverage

Contract bundle: `9b1659218aa56bbbf542bf55d9475c7cf16ae036b531c72c099adc738203d439`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 193 | 193 | 193 | 184 | 9 | 193 | 138 | 53 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 46 | 37 | 9 | 46 |
| Worker | 21 | 21 | 0 | 21 |
| Service | 126 | 126 | 0 | 126 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
