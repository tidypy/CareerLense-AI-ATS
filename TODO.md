# TODO: LLM Interrupt & Loop Resolution

This document tracks the immediate technical tasks required to fix the LM Studio looping/interrupt issue.

## High Priority 🚨

### Backend (Python/FastAPI)
- [ ] **[llm_service.py]**: Instantiate `threading.Event()` registry for client IP tracking.
- [ ] **[llm_service.py]**: Add `stop` parameter to `LocalLLMClient.generate_json` with tokens: `\n\n\n`, `json`, ` ``` `.
- [ ] **[llm_service.py]**: Rewrite `LocalLLMClient.generate_json` to iterate over `client.chat.completions.create(..., stream=True)`.
  - [ ] Check `cancellation_event.is_set()` in every iteration and break/raise if True.
- [ ] **[main.py]**: Implement `POST /api/v1/interrupt` endpoint.
  - [ ] Find matching IP in registry and trigger `.set()`.
- [ ] **[main.py]**: Refactor `_do_generate` to be `async` or use `anyio` to ensure it doesn't block the event loop for the interrupt endpoint.

### Frontend (Flutter)
- [ ] **[main.dart]**: Modify the `ElevatedButton` for "INTERRUPT GENERATION".
  - [ ] Add `await http.post(Uri.parse("$_backendUrl/interrupt"))` task before client closure.

## Future Considerations 🕒
- [ ] **Dynamic Stop Tokens**: Auto-inject tokens based on the current JSON schema depth.
- [ ] **Timeout Guard**: Implement a server-side hard timeout that triggers the cancellation event automatically.
- [ ] **Slot Management API**: Integrate direct call to LM Studio's `/slots/action` endpoint for hard aborts.
