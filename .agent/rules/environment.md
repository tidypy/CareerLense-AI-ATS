---
trigger: always_on
---

# Fail Fast & Environment Guard

* **Error Threshold:** If any terminal command (e.g., flutter, docker, java) fails twice with the same error, STOP immediately. Do not attempt to "self-heal" or search for fixes without asking me.
* **Dependency Lock:** Do not attempt to download, install, or update system-level software (like JDK, Docker Desktop, or WSL) autonomously. If a version is missing or incorrect, report it to me and wait.
* **Windows Terminal Fix:** Always use `cmd /c` prefix for shell executions to ensure the process terminates correctly and sends an EOF signal. This prevents the "Running..." hang state.
* **Agnostic Builds:** When creating Docker files, ensure they are multi-stage and do not rely on my local Downloads folder path.