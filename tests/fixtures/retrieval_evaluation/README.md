# Synthetic ranked results for the Week 4 scorer

`synthetic_week4_rankings.json` contains deliberately fabricated rankings and
timings for the preserved human checkpoint. It does not add or change any
reference label and is **not a vector-retrieval baseline**. No embedding or
search service produced these results.

The four answerable cases have hit scores `1, 0, 1, 1`, recalls `1, 0, 0.5, 1`,
and reciprocal ranks `0.5, 0, 1, 0.5`. Their expected averages are therefore
`0.75`, `0.625`, and `0.5`. Repeated billing-plan chunks count as one document.
One of the six cases without relevance labels returns a chunk; this is reported
descriptively and is not scored as answer abstention.

The search times 1 through 10 ms and embedding times 2 through 20 ms are fake.
Tests cover malformed/stale data, missing results, failures, privacy boundaries,
checkpoint preservation, deterministic reports, and deliberate regressions.
The hand-written result fixture must never be promoted to measured evidence by
changing its `evidence_kind` marker.
