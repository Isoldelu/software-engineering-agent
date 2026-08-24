# Context And Trace Evaluation Report

## Dataset

- 8 multi-turn conversations
- 18 total turns
- 10 context-dependent follow-up turns
- 5 cross-session isolation probes
- Package, release, component ownership, Chinese aliases, and English pronouns

## Results

| Metric | Result |
|---|---:|
| Entity consistency | 100% |
| Cross-session leak count | 0 |
| Cross-session leakage rate | 0% |
| Trace completeness | 100% |
| Replay input reconstruction | 100% |
| Bad cases after fixes | 0 |

## Bad-case Findings

1. The first completeness check searched serialized Trace text for the word `thought`, so it incorrectly rejected the explicit privacy declaration `stores_internal_thought=false`. The check now detects only an actual `thought` field.
2. The first resolver treated every query containing `版本` as a package follow-up. `这个版本的发布说明` therefore inherited both release and the last package. Release-reference detection now takes precedence and only inherits release unless a package is explicitly referenced.
3. One tcpdump evaluation fixture expected old version `4.90`, while the simulated source record contains `4.95`. The fixture was corrected against the source data.

## Acceptance

All Step 21 thresholds pass. The Step 17 compatibility baseline and the original 193 single-turn evaluation cases remain unchanged.
