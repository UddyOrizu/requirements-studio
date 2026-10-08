---
name: intake_phrase
module: M0
output_model: IntakeQuestion
variables: [target, slot_key, gap, ir_summary, recent_turns, requester_role, mode]
temperature: 0
---
Write the next interview question for a {{requester_role}} describing their own idea.
- Mode {{mode}}: if "as_is", ask about how the work is done TODAY ("Today, who…", "How long does… take now?"), not how it should be.
  For pain_points (C17), ask where the time goes and roughly how many minutes each step takes.
- One question, ≤ 35 words, plain business English, no jargon about models, IR or slots.
- Build on what they already said (use their words); never ask for something already known.
- Add "why" (≤ 20 words): why this matters for the automation.
- Offer 2–4 suggested answers that are realistic for this process (the system appends Other / Not sure / Skip).
- For happy_path (C06), play back the current steps in one line and ask what's missing or out of order.
- For human_controls (C16), list the steps briefly and ask which can run automatically, which a person must review, and
  where someone must approve before the flow continues.
Return {text, why, answer_type, suggested_answers}.
<data>
target: {{ target }}
slot_key: {{ slot_key }}
gap: {{ gap }}
ir_summary: {{ ir_summary }}
recent_turns: {{ recent_turns }}
</data>
