# Unified SDK operation coverage

Contract bundle: `eb5a6a016b1efa62f0f720847888fc31575c5b7c797a6d5b4814bfbba07ccd1d`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 140 | 140 | 140 | 131 | 9 | 140 | 110 | 28 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 | 45 |
| Worker | 12 | 12 | 0 | 12 |
| Service | 83 | 83 | 0 | 83 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
