---
name: _validation_retry
module: S1
description: Appended by the LLM gateway when a response fails validation; the call is retried once.
variables: [validation_error]
---
Your previous response was not valid. It failed with:
<data>{{ validation_error }}</data>
Respond again with JSON only, matching the schema exactly.
