# Slice 12.15 — LLM generation memory isolation

Observed long acceptance runs could make the local LLM worker resident RAM jump by
many GiB after later requests.  The diagnostic batch was also invoking the full LLM
Agent after every parser case even though agent prose is not part of perception/T/N
acceptance.

Changes:

- `LLMRoleSettings` now has an explicit `use_cache` policy.
- `[llm.perception].use_cache = false` by default.  Adaptive perception probes are
  short, stateless classifications; they do not retain or require KV-cache speedups.
- `[llm.agent].use_cache = true` remains the normal interactive policy for longer
  generated answers.
- `ah.llm.worker` treats all generation tensors/cache state as request-local and
  drops references in a `finally` block.  For cache-enabled CUDA generation it also
  releases unoccupied CUDA allocator blocks after the request.
- `AgentOrchestrator.handle_user_text(..., generate_response=False)` is an explicit
  diagnostics mode.  It executes the normal sensory -> perception -> integration ->
  ignition -> inference -> projection path and stops at `AgentContext`; it does not
  invent an empty/synthetic response and therefore writes no response event to H.
- The file-driven acceptance runner uses that diagnostics mode.  It still records
  `AgentContext`, queries/inference, AH diff, runtime/context state and all parser/LLM
  probe diagnostics, but it no longer spends one large agent-generation request per
  case or pollutes H with unrelated generated answers.

Normal GUI interaction is unchanged: user turns still go through LLM Agent and the
actual agent utterance is recorded in H according to the architecture.
