# Unified SDK operation coverage

Contract bundle: `5b44c873737a135f75486b56f84cd534c0ac398dc87cdbc0150fd64c8cfcfcbd`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 130 | 130 | 130 | 121 | 9 | 130 | 104 | 24 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 | 45 |
| Worker | 12 | 12 | 0 | 12 |
| Service | 73 | 73 | 0 | 73 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
