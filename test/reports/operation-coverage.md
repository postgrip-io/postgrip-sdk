# Unified SDK operation coverage

Contract bundle: `c88f2c1532abd35e1c7f8f0c6103def1db9ed77110ae2927ad363be56d810c2a`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 143 | 143 | 143 | 134 | 9 | 143 | 111 | 30 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 | 45 |
| Worker | 12 | 12 | 0 | 12 |
| Service | 86 | 86 | 0 | 86 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
