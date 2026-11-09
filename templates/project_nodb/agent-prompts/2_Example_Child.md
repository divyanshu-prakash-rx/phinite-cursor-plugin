You <do one specialised job> using `<input variable>` (e.g. the extracted document pages).

<What to compare / write, in 3–6 bullets.>

Return ONLY this JSON (no other text):
{"facts": [{"field": "...", "value": "...", "doc": "<file>", "page": <n>}],
 "discrepancies": [{"description": "...", "doc": "<file>", "page": <n>, "severity": "high|low"}]}
Use "high" only for <the cases that must block>. Cite only what is present in the input.

Store the JSON in `<capture variable name>` with **StoreVariableTool**.
