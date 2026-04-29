flowchart TD
  Start["START"] --> MR["MemoryRetrieveNode\n- fetch past attempts\n- fetch promises/disputes"]
  MR --> RN["ReactNode\n- plan next step for current turn\n- select tool_name + arguments when needed\n- or choose direct response"]
  RN -->|route: act| TE["ToolExecutionNode\n- executes chosen tool with arguments"]
  RN -->|route: respond| RF["ReflectNode\n- summarize final context\n- write memory/audit once per turn"]
  TE --> RN
  RF -->|route: incomplete| RN
  RF -->|route: complete| RS["ResponseNode\n- generate compliant customer reply"]
  RS --> End["END"]

  subgraph TBOX["Tools Available To ToolExecutionNode"]
    T1["case_fetch"]
    T2["case_prioritize"]
    T3["contact_attempt"]
    T4["customer_verify"]
    T5["loan_policy_lookup"]
    T6["dues_explain_build"]
    T7["offer_eligibility"]
    T8["payment_link_create"]
    T9["payment_status_check"]
    T10["promise_capture"]
    T11["followup_schedule"]
    T12["disposition_update"]
    T13["human_escalation"]
    T14["negotiation_agent_tool"]
    T15["qa_review_agent_tool"]
    T16["dispute_triage_agent_tool"]
  end

  TE -.uses.-> TBOX
