# Unified SDK operation coverage

Contract bundle: `b728fee5bceb4d246fe7ce81c1583d228d4f16d8f530179950fd5dccb2954820`

| Operations | Documented | SDK-generated | cURL | Protocol exceptions | Recorded-tested | Nightly-live | Pre-release-live | Production-smoke |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 130 | 130 | 130 | 121 | 9 | 130 | 121 | 7 | 2 |

| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |
| --- | ---: | ---: | ---: | ---: |
| Agent | 45 | 36 | 9 | 45 |
| Worker | 12 | 12 | 0 | 12 |
| Service | 73 | 73 | 0 | 73 |

Every operation is documented, owned by generated clients in all three languages, and exercised by a recorded runner. Protocol exceptions are visible and are not counted as cURL coverage.
