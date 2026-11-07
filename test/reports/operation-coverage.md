# Unified SDK operation coverage

Contract bundle: `0fd58ddbe2da2928c78655bb5d3909020acb547de2f6959e9acb7181e8e81047`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 189 | 189 | 189 | 180 | 9 | 189 | 136 | 51 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 46 | 37 | 9 | 46 |
| Worker | 19 | 19 | 0 | 19 |
| Service | 124 | 124 | 0 | 124 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
