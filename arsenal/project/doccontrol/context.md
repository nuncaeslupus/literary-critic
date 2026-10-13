# doccontrol: Context

Move every .docx read/write in literary-critic onto the doc-control package (pinned runtime dep, vendored in the kit). Keep only literary logic here: cNN.sN.pN labels, Codex/spans, checks, rounds, reports, prompts, metrics, setup, kit. Never build what doc-control owns (live Word, .odt, MCP, generic diff/redline); raise gaps with doc-control instead. Spec: arsenal/project/doccontrol/spec.md.
