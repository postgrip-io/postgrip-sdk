# Unified SDK operation coverage

Contract bundle: `11ab5c645b5ba2b87e37ebdd1dd90abbcbe47b5927a8f68607cd3d1ca5dbfbfe`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 187 | 187 | 187 | 178 | 9 | 187 | 135 | 50 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 46 | 37 | 9 | 46 |
| Worker | 19 | 19 | 0 | 19 |
| Service | 122 | 122 | 0 | 122 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
