# Development exposure record

Date: 2026-10-19. No held-out predictions have been run in this work session.

- Read both manuscript planning material and release documentation. The medical-tray worked example is held-out current CA-0001 (historical CA-0007), so it must not become a prompt demonstration.
- Inspected the first source/native/route row (CA-0001) to establish schemas and approval scope. Read current/historical IDs and abbreviated descriptions for the three approved route corrections and CA-0100 in release documentation. These inspections were for provenance and isolation, not model selection or prompt comparison.
- Mechanical preparation and integrity tests read all source/reference rows to map fields, compare bytes and verify count/ID/hash consistency. This is not blinded task-reference adjudication.
- Development examples are newly authored in `development/`. They are not drawn from the manuscript worked example or copied from a protected record. No held-out case may be moved into development; semantic overlap still needs independent screening before the final protocol freeze.
- Local smoke outputs are explicitly MOCK_DEVELOPMENT or LIVE_DEVELOPMENT. The routing scorer rejects both. Mock success provides no accuracy or provider-access evidence.
- The version 1.0.1 count terminology change follows the user's request to count all 100 current inputs as source records; input/route/archive hashes are unchanged. Historical origins remain separately recorded.

Any later exposure, code/config amendment or reference revision must be recorded before evaluating it; do not claim that an audit exposure was blind.
