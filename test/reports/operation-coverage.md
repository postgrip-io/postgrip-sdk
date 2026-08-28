# Unified SDK operation coverage

Contract bundle: `7d1702e54be36871b78b433fae3edcb261c6ea191a0fe238ab9bcb1bea872d43`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 146 | 146 | 146 | 137 | 9 | 146 | 112 | 32 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 | 45 |
| Worker | 13 | 13 | 0 | 13 |
| Service | 88 | 88 | 0 | 88 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
