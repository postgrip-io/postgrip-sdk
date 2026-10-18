# Unified SDK operation coverage

Contract bundle: `449013ff4353f04b4575140417b29c823749ece0747ffaea04bceb79464a59f8`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 177 | 177 | 177 | 168 | 9 | 177 | 131 | 44 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 | 45 |
| Worker | 13 | 13 | 0 | 13 |
| Service | 119 | 119 | 0 | 119 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
