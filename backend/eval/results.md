# Evaluation results

Golden set: 15 pairs (7 generation, 8 behavioural)

### RAGAS (generation pairs)

Judge LLM: `gpt-4.1-mini` (LangchainLLMWrapper). Pairs scored: 7

| metric | score |
|---|---|
| faithfulness | 0.845 |
| answer_relevancy | 0.744 |
| context_precision | 0.976 |
| context_recall | 1.000 |


### Retrieval (ground-truth sources present in context)

| question | expected | hit | multi-hop | via_reference present | confidence |
|---|---|---|---|---|---|
| What formats can a finished structure be exported as? | doc_04 | PASS | no | yes | 0.0333 |
| How many generations per day does the Free tier allow and wh | doc_05 | PASS | no | no | 0.0333 |
| What confidence score causes a build to be tagged review rec | doc_07 | PASS | no | no | 0.0333 |
| How do I get an API key and which tier is required? | doc_09 | PASS | no | yes | 0.0333 |
| How many reference builds do I need to upload for a custom s | doc_03 | PASS | no | yes | 0.0331 |
| Which known issue caused the ticket about a generation stuck | ticket_101, doc_12 | PASS | yes | yes | 0.0333 |
| The ticket about floating coral chunks matches which known i | ticket_105, doc_12 | PASS | yes | yes | 0.0333 |

Reference-expansion pairs passing (both docs in context AND a via_reference source): 2/2


### Behavioural accuracy (aggregation / abstain / tool paths, via /agent)

| question | expected | got | pass |
|---|---|---|---|
| Which support tickets resulted in a refund? | aggregation | answer | PASS |
| Which ticket was NOT closed as expected behavior? | aggregation | answer | PASS |
| How many tickets were closed as expected behavior? | aggregation | answer | PASS |
| How do I install a Kubernetes ingress controller on bare met | abstain | abstain | PASS |
| What uptime SLA does Craftify guarantee on the Studio tier? | abstain | abstain | PASS |
| Can I pay for my Craftify subscription with PayPal? | abstain | abstain | PASS |
| File a support ticket about my underwater build generating f | tool_call | tool_call | PASS |
| Create a ticket | clarify | clarify | PASS |

Behavioural accuracy: 8/8 = 100%

Abstention accuracy on unanswerable subset: 3/3
