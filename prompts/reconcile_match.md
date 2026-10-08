---
name: reconcile_match
module: M2
output_model: MatchDecision
variables: [element_type, candidate, existing]
temperature: 0
---
Decide whether the candidate describes the same {{element_type}} as any existing element.
Return {match_id|null, decision: same|different|same_but_conflicts, conflicting_fields[], reasoning (≤ 2 sentences)}.
"same_but_conflicts" means it is the same step/actor/rule but the sources state different facts
(e.g. a different performer, threshold or duration).
<data>candidate: {{candidate}}
existing: {{existing}}</data>
