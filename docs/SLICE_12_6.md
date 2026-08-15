# Slice 12.6 — GUI turn lifecycle, S visualization, live LLM diagnostics

- Chat submission now keeps the active QRunnable alive explicitly and performs UI cleanup through a MainWindow Qt slot. The send button/input are restored after every success or error, so consecutive turns are supported.
- LLM tabs are scoped to the most recently submitted GUI turn. Parser RAW/decoded, Agent RAW and Requests no longer display stale data from the preceding turn while a new turn is running. Completion triggers an immediate refresh in addition to periodic polling.
- Worker log now receives one concise completion/error line for every LLM role request.
- GUI graph suppresses orphan lexical/sensory S elements. S referenced by a visible structural edge (for example T -> S predicate) or canonical L remains a real visible node. Canonical AH storage and sensory processing are unchanged.
- Runtime status reports rendered node count separately from hidden orphan lexical S count.
- Regression coverage includes orphan-S filtering and preservation of structurally connected predicate S.
