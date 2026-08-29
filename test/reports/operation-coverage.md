# Unified SDK operation coverage

Contract bundle: `aa2e7e8b6f0156a7234bed7053b7669c9fdd3798f0cb366afafeb1400ccb35b4`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 168 | 168 | 168 | 159 | 9 | 168 | 124 | 42 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 | 45 |
| Worker | 13 | 13 | 0 | 13 |
| Service | 110 | 110 | 0 | 110 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
