# Slice 11.1

Perception robustness patch for weak local models.

- Numeric option rendering no longer uses `N = description`; options are shown as `[N] description`.
- Token lists use `[N] token` instead of `N=token` to reduce completion/echo priming.
- Numeric validators accept only format-only wrappers such as `1.`, `[1]`, `(1):`, or `1 =`.
- Explanatory text such as `I choose 1` or `1 = claim` is still rejected.
- Single-digit enum probes use a one-token generation budget where possible.
- Micro-prompts now explain the expected numeric answer with concrete wording instead of meta-notation.
