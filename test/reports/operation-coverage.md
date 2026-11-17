# Unified SDK operation coverage

Contract bundle: `e05a31a1a8648663c2cc10b11a1dfd7c229c7faef6a885395bf4900852842bbc`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 203 | 203 | 203 | 194 | 9 | 203 | 138 | 63 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 53 | 44 | 9 | 53 |
| Worker | 22 | 22 | 0 | 22 |
| Service | 128 | 128 | 0 | 128 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
