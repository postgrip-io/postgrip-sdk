# Unified SDK operation coverage

Contract bundle: `511df92979949a35b20dfe1cdb4da3384325a4d794b0d7370ae3a8ff7a2b25f0`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 203 | 203 | 203 | 194 | 9 | 203 | 138 | 63 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 53 | 44 | 9 | 53 |
| Worker | 22 | 22 | 0 | 22 |
| Service | 128 | 128 | 0 | 128 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
