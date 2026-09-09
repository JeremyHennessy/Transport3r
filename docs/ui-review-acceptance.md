# UI review acceptance checklist

This checklist is intentionally kept with the UI branch so visual changes are evaluated as a release, not inferred from a merge.

- TypeScript typecheck passes.
- Existing JavaScript/Python data-integrity tests pass.
- Production Vite build passes.
- Existing Carrier 360 browser regressions pass.
- Date-window and map browser regressions pass.
- Existing report/PDF fixtures pass after chart/map markup changes.
- Carrier directory renders without page overflow on desktop and mobile.
- Summary, Safety, Fleet, Authority, Insurance, SMS, Evidence, Inspection and VIN routes render without runtime fallback.
- Recent Safety map renders state-level inspection/crash evidence without geocoding.
- Selected-window map preserves source-window semantics and event drillthrough.
- Pages deploys the exact merged SHA.
- Hosted release manifest verifies the exact SHA and artifacts.
- Fresh hosted screenshots are captured and reviewed before calling the UI work complete.
