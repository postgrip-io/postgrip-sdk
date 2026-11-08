# Unified SDK operation coverage

Contract bundle: `33186029f5e0ef1b7f6d4c7d1a8ac537828dcea67c8a0520ff273b2add082759`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 195 | 195 | 195 | 186 | 9 | 195 | 138 | 55 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 46 | 37 | 9 | 46 |
| Worker | 21 | 21 | 0 | 21 |
| Service | 128 | 128 | 0 | 128 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
