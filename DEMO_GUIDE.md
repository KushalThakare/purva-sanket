# PURVA SANKET — Judge demonstration

## What is live and what is simulated

- Wokwi sensors, injected vibration, airflow feedback and actuator feedback are
  virtual test inputs. No physical motor or stop physics are simulated.
- Offline mode uses labelled synthetic telemetry and an actuator model.
- YOLO/ByteTrack observations are actual video inference only when the optional
  worker has been started and verified. Scripted presence is labelled separately.
- Isolation Forest models use synthetic normal windows for three selected modes.
- Operating mode is selected by an operator. Rules govern critical demo actions.

## Start

Run scene 1, select Production, keep the GPIO35 feedback switch LEFT, and clear
all test faults. Wait for AVAILABLE monitoring, normal ML and confirmed STOP.
Click Start / restart to request RUN.

## Original six scenes

1. **Normal:** establish valid inputs and a command/feedback handshake.
2. **Weak warnings:** allow repeated vibration crossings and changing temperature
   to accumulate in the same episode.
3. **Cooling mismatch:** command ON but feedback absent; the defined temperature
   condition requests and verifies a simulated STOP.
4. **Worker exposure:** presence joins existing equipment evidence.
5. **Sensor failure:** monitoring becomes degraded while earlier evidence remains.
6. **Recovery:** return inputs to normal, acknowledge, record corrective action
   and require confirmed STOP plus 15 seconds of valid recovery. Restart is separate.

The 10-sample window may also need to rebuild. An episode can remain open while
the comparison cards show no current warning: the cards and episode have
different purposes.

## Extra ML demonstration

Use **ML pattern below fixed limits** from normal Production monitoring. Its
synthetic profile changes temperature from 35 to 36.08°C and holds vibration at
0.22 m/s². With roughly one sample per second the slope stays below the explicit
0.15°C/s rule, temperature below 45°C, and vibration below 0.45 m/s².

The model can flag departure from its synthetic baseline while these rules do
not warn. The comparison cards use the same accepted inputs, trend rule,
protective states, worker context and monitoring-health checks; only model
evidence differs. Acquisition timing affects the measured slope.

Read **first warning** and **warning samples**. If only hybrid warned, the UI
reports that directly instead of inventing a numerical time advantage. This is
a model contribution demonstration, not proof of accident prediction or
superiority to all possible rule configurations.

To recover afterward, select scene 6, request and verify STOP, acknowledge,
record the correction, wait for closure, then restart explicitly.

## Interactive fault tests

| Button | Pipeline behavior | Expected observation |
|---|---|---|
| Temperature missing | Temperature becomes null/invalid before feature extraction | ML unavailable; degraded monitoring |
| Camera unavailable | Presence observations invalidated | Exposure unknown; recovery blocked |
| Cooling feedback absent | Feedback input overridden, command retained | Explained mismatch; stop when the configured condition applies |
| Telemetry delayed | Inputs buffered 8 seconds; aged packets rejected using their known ingress times | Health becomes degraded after the 6-second freshness allowance |
| Repeat last packet | The old session/sequence is replayed | Rejected duplicates cannot refresh health |
| Acknowledgement missing | Matching command acknowledgement suppressed | Response unconfirmed at the 8-second demo deadline |
| Motor feedback unavailable | Feedback validity removed | Acknowledgement alone cannot confirm the response |
| Feedback reports running | Separate injected feedback says RUNNING | STOP request remains unconfirmed |

Response-fault buttons request a fresh STOP so each test has a new command ID.
Clear test faults to restore incoming observations. Clearing a fault or clicking
acknowledge does not erase an episode or restart the output.

The GPIO35 switch is an alternative way to inject mismatched feedback in Wokwi.
Return it LEFT before recovery. It is separate from dashboard fault buttons.

## Evidence and persistence

- **Response commands:** IDs, device session, request/publication/deadline times,
  acknowledgement, confirmation, status and explanation in SQLite.
- **Events:** fault changes, contributing evidence and recovery.
- **Comparison runs/samples:** current-evidence results on identical accepted
  input samples, with injected-fault labels.
- **CSV:** Download comparison CSV includes up to the latest 10,000 observations.
- Restarting the backend keeps episode history but requires a new STOP handshake.
  Previous command IDs and duplicate observations cannot confirm a new request.
- Fault toggles reset on backend restart; recorded fault events remain.

## Evaluate the prototype

Reserve complete synthetic replay runs for evaluation. Include unseen normal
variation as well as scripted deviations, and record the mode and fault settings.
Measure warning onset, warning starts during labelled normal runs, input-loss
detection and request-to-confirmation time. Keep training and evaluation runs
separate. Do not label warning counts as industrial accuracy.

The fault panel tests software behavior. It does not perform certified proof
testing or establish industrial safety compliance.
