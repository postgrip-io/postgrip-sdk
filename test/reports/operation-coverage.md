# Unified SDK operation coverage

Contract bundle: `2b2b07aa61a7b55da13ae193ea427ffe2823e4ff614b99e1f183224b93e826bd`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 135 | 135 | 135 | 126 | 9 | 135 | 108 | 25 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 | 45 |
| Worker | 12 | 12 | 0 | 12 |
| Service | 78 | 78 | 0 | 78 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
