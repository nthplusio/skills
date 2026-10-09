# Disposable local implementation exercise

Copy this whole directory to a temporary workspace before editing. The source
`gate.py` is deliberately broken: it treats failed, cancelled, and missing
prerequisites as successful, and accepts unvalidated skips. Fix only the copy.
`expected` names all gate participants. A skip is permitted only when
`selection_valid` is true and that task appears in `allowed_skips`.
Run `python3 check_gate.py` from that copy. No dependencies or hosted access are
needed. Cases cover success, justified skip, failed, cancelled, missing, and
invalid-selection states.
