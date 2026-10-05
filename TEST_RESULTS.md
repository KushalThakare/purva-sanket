# PURVA SANKET 2.0 demo — Verification

Verified on 4 October 2026. Results describe the software simulation and do not
establish real equipment response or industrial performance.

## Backend and migration

**27 automated tests passed** using Python 3.12.14. Coverage includes:

- The six original scenarios, retained warning evidence, mode rules,
  acknowledgement, corrective action and interrupted recovery.
- Missing acknowledgements, unavailable or mismatched motor feedback,
  wrong command IDs and fresh STOP handshakes after backend restart.
- Stale and duplicate packets, delayed/repeated fault inputs, sensor loss
  and camera loss. Rejected observations cannot refresh monitoring health.
- Same-input rules/ML comparison, shared critical checks, the synthetic
  below-limit anomaly and CSV export.
- FastAPI routes and a local MQTT broker round trip with synthetic protocol
  telemetry.
- Existing SQLite episode preservation and the Windows upgrade helper's
  topic, port, data-copy and destination-overwrite checks.
- Video observation geometry and labels; these tests do not run YOLO inference.

One non-failing Starlette TestClient deprecation warning was emitted.

## Dashboard in a browser

Headless Chromium checks passed against the running FastAPI application in
offline simulation mode:

1. Fresh STOP confirmation, normal monitoring and confirmed RUN after restart.
2. The motor-feedback fault button, response timeout and a held STOP command.
3. Clearing the fault, recording an action, acknowledgement and episode closure
   only after sustained recovery.
4. The extra synthetic ML scene: the hybrid path warned while the selected
   explicit rules remained clear on the same observations.
5. CSV download and the read-only runtime checker.
6. Desktop layout at 1365 px and mobile layout at 390 px, with no horizontal
   page overflow or uncaught JavaScript errors. Screenshots were inspected.

The model result is a synthetic demonstration of contribution beyond this rule
set. It is not an accuracy, prediction or comparison claim about deployed systems.

## ESP32 and source checks

- PlatformIO ESP32 build succeeded with Espressif32 7.1.3 and Arduino ESP32
  core 2.0.17. RAM: 45,756 bytes (14.0%). Flash: 811,941 bytes (61.9%).
- Two non-failing warnings came from the OneWire dependency.
- The Wokwi diagram has 37 unique parts and 47 connections; connection part
  references and the GPIO35 feedback-switch connections were checked.
- Python syntax compilation and JavaScript syntax checks passed.

## Checks to perform on the presentation laptop

This environment did not run Docker Desktop, the hosted Wokwi project or actual
camera inference. Complete UPGRADE.md on the Windows laptop, then verify the
Docker container, matching MQTT topic, Wokwi command/feedback handshake and any
optional video worker before presenting. The public broker requires network
access. A labelled offline fallback is included.

The response model and GPIO35 switch supply simulated feedback. A confirmed
response does not measure motor deceleration or prove a physical stop.
