# PURVA SANKET — Upgrade your working Windows project

This update adds command/feedback verification, eight fault tests, a same-input
rules/ML comparison, CSV export and an extra below-limit ML scenario. The six
original scenes remain. Settings and SQLite history can be copied forward.

## 1. Extract into a new folder

Extract the updated ZIP into **C:\Users\SUJEET\Downloads\Purva_Sanket_Upgrade**.
The inner project should be:

**C:\Users\SUJEET\Downloads\Purva_Sanket_Upgrade\purva-wokwi-starter**

Use a fresh directory. Keep your working old project as a backup.

## 2. Stop the old containers before copying SQLite

In Windows PowerShell:

~~~powershell
$oldProject = "C:\Users\SUJEET\Downloads\Purva_Sanket_Wokwi_AI_Starter\purva-wokwi-starter"
Set-Location $oldProject
docker compose down
~~~

This stops the writers. It keeps your host data folder.

## 3. Copy settings, history and available video/models

~~~powershell
Set-Location "C:\Users\SUJEET\Downloads\Purva_Sanket_Upgrade\purva-wokwi-starter"
docker run --rm -v "$($PWD.Path):/workspace" -v "${oldProject}:/previous:ro" -w /workspace python:3.12-slim-bookworm python upgrade_settings.py --from /previous
~~~

The helper copies **.env**, **topic.txt**, **data**, and any **media** or **models**
directories. It keeps your MQTT topic and existing web-port setting. It modifies
the new sketch's topic to match. Your original directory is preserved.

If your previous folder is elsewhere, change only **$oldProject**. The helper
requires that path to contain **compose.yaml** and **backend\engine.py**.
It refuses to overwrite an already populated destination data/media/models
directory; use a fresh extraction in that case.

Without a previous project, follow DOCKER_SETUP.md and configure_topic.py instead.

## 4. Update both Wokwi files

1. Open your existing Wokwi project and stop its simulation.
2. Replace the complete **sketch.ino** with the upgraded **wokwi\sketch.ino**.
3. Replace the complete **diagram.json** with the upgraded **wokwi\diagram.json**.
4. Keep the dependencies in **wokwi\libraries.txt** installed.
5. Check that **TOPIC_BASE** matches **PURVA_TOPIC** in the new **.env**.
6. Save, then start Wokwi.

Updating only TOPIC_BASE is insufficient for this upgrade: command IDs,
acknowledgements and feedback fields are new. The diagram adds a simulated
running-feedback switch on GPIO35 with an external 10 kΩ pull-up.

Keep this new switch **LEFT = NORMAL** for ordinary demonstrations. RIGHT
deliberately reports running even when the blue output indicator is off.
The switch works in every scene.

## 5. Build and run the upgraded backend

~~~powershell
docker compose config
docker compose up -d --build backend
docker compose logs --tail 50 backend
~~~

With your existing **PURVA_WEB_PORT=8001**, open:

- Dashboard: http://127.0.0.1:8001
- API: http://127.0.0.1:8001/docs

If .env uses a different web port, use that value. The internal Docker port
remains 8000.

Hard-refresh the browser with **Ctrl+F5**. New database tables are created
automatically; old episodes, actions and observations remain.

## 6. Verify before presenting

1. Keep scene 1 running and all fault-panel buttons off.
2. Response verification should progress to **CONFIRMED**, target **STOP**,
   feedback **STOPPED**.
3. Wait for normal ML and AVAILABLE monitoring.
4. Click **Start / restart**. The RUN command then requires matching feedback.
5. Select scene 3. Verify STOP and retain the episode ID.
6. Check the new panels using DEMO_GUIDE.md.

**PROTOCOL REQUIRED** means old firmware is still supplying telemetry.
**UNCONFIRMED** means acknowledgement/feedback is missing or does not match.
A confirmed output is simulation evidence, not a certified physical stop.

## Offline fallback

~~~powershell
docker compose -f compose.yaml -f compose.offline.yaml up -d --build backend
~~~

The backend runs a labelled synthetic actuator model and all new panels. To
return to Wokwi, keep **PURVA_INPUT_MODE=mqtt** in .env and run:

~~~powershell
docker compose -f compose.yaml up -d backend
~~~

For the optional video worker, use the existing DOCKER_SETUP.md instructions.
