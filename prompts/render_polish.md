---
name: render_polish
module: M7
output_model: PolishedStory
variables: [story, closure_terms]
temperature: 0
---
Improve the wording of i_want and so_that for a business reader. Keep meaning identical.
Use only terms from closure_terms for nouns. Do not add new facts, numbers, systems or roles.
<data>
story: {{ story }}
closure_terms: {{ closure_terms }}
</data>
