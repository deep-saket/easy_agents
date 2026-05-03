# Sample Conversations

## Conversation A: Verification incomplete, dues disclosure blocked

1. Agent: "This is Alex from the bank collections team regarding your overdue amount of INR 12500. Are you available to discuss payment today?"
2. Customer: "Sorry for the delay, how can you help me?"
3. Agent: "Before I share details, please confirm your identity with your full name, DOB, PAN last 4, and ZIP."
4. Customer: "My name is Aditi Sharma"
5. Agent: "Thank you, Aditi Sharma. To complete verification, please also share your date of birth (YYYY-MM-DD), the last 4 characters of your PAN, and your registered ZIP/pincode."

Expected graph behavior:

- current node remains `verify_identity`
- marker for `verify_identity` remains `pending`
- no dues explanation until successful `customer_verify`

## Conversation B: Verification complete and payment intent

1. Customer: "DOB 1991-08-19, PAN last 4 AF4K, ZIP 560102"
2. Agent: "Thank you, verification is complete. Your total due is INR 13350. Would you like to pay now?"
3. Customer: "Yes, send payment link on SMS"
4. Agent: "Done. I can generate the link now."

Expected tool path:

- `customer_verify` -> `verified`
- `dues_explain_build`
- `payment_link_create`

## Conversation C: Hardship branch

1. Customer: "I cannot pay full amount this week, can you reduce EMI?"
2. Agent: routes to assistance path
3. Agent: evaluates eligibility and proposes plan
4. Customer: accepts plan and asks for follow-up date
5. Agent: captures promise and schedules follow-up

Expected tool path:

- `offer_eligibility`
- `plan_propose`
- `promise_capture`
- `followup_schedule`

## Conversation D: Out-of-scope

1. Customer: "What is today’s weather?"
2. Agent: "This request is outside collections scope..."

Expected graph behavior:

- `relevance_intent` -> `irrelevant`
- `irrelevant_response`
- terminal
