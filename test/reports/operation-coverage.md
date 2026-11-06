# Unified SDK operation coverage

Contract bundle: `25b5b43e3695f74e5388f060ade3e005d5791cfa42fba3f4a7a9cba1db2a72f6`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 180 | 180 | 180 | 171 | 9 | 180 | 131 | 47 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 | 45 |
| Worker | 13 | 13 | 0 | 13 |
| Service | 122 | 122 | 0 | 122 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
