# API and Frontend

**Status:** planned (TASK-21 to TASK-23). The full endpoint contract is in plan Task 21. When endpoints land, list them here with their route file.

## Endpoints
_None yet._

## SSE contract
Event types `frame | event | cue | insight | end`. `id = "{period}:{t:.1f}:{seq}"`. Resuming with `Last-Event-ID` or `from_t` must give no duplicates.

## Frontend
_Design direction: not chosen yet (TASK-22)._ Components are listed here as they land, with their path and what they consume.
