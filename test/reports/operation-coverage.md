# Unified SDK operation coverage

Contract bundle: `87c0db92da44a39eb7a85c5f5b39186dbebc8e8f243cab5e1462838c7742a017`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 185 | 185 | 185 | 176 | 9 | 185 | 133 | 50 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 | 45 |
| Worker | 18 | 18 | 0 | 18 |
| Service | 122 | 122 | 0 | 122 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
