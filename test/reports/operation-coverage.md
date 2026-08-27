# Unified SDK operation coverage

Contract bundle: `f9ea05cd07831a2785b4b5e0bf3f97c1c83458a22e7e138a576044b791b6b903`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 144 | 144 | 144 | 135 | 9 | 144 | 111 | 31 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 | 45 |
| Worker | 13 | 13 | 0 | 13 |
| Service | 86 | 86 | 0 | 86 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage. Live columns are cadence ownership only; passing live evidence is carried by workflow cleanup-ledger artifacts.
