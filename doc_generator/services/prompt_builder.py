def build_prompt(policy_template, controls, context):
    """
    Builds a formatted prompt string based on the policy template
    and mapped controls.

    policy_template = PolicyTemplate instance
    controls = queryset/list of Control objects
    context = dict with ORG_NAME, ORG_SIZE, ENVIRONMENT, MAX_WORDS
    """

    # Build control summary
    control_lines = []
    for c in controls:
        desc = (c.description[:200] + "...") if c.description else ""
        control_lines.append(f"- {c.control_id}: {c.title} {desc}")

    control_summary = "\n".join(control_lines)

    # Pick template text (fallback if missing)
    if policy_template.prompt_template:
        template_text = policy_template.prompt_template.template
    else:
        template_text = (
            "SYSTEM: You are an ISO 27001:2022 security policy writer.\n\n"
            "USER: Draft the policy '{POLICY_NAME}' for {ORG_NAME}.\n\n"
            "Mapped Annex A controls:\n{CONTROL_SUMMARY}\n\n"
            "Context:\n- Size: {ORG_SIZE}\n- Environment: {ENVIRONMENT}\n\n"
            "Include sections: Purpose, Scope, Policy Statement, Roles & Responsibilities, "
            "Monitoring & Review.\n"
            "Tone: formal security governance. Limit to {MAX_WORDS} words.\n"
            "Finish with a 'Control trace' mapping sections to controls."
        )

    # Substitute placeholders
    final_prompt = template_text.format(
        POLICY_NAME=policy_template.name,
        CONTROL_SUMMARY=control_summary,
        **context
    )

    return final_prompt

