from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

class Control(models.Model):
    """
    Represents a single Annex A control (e.g., A.5.1)
    """
    control_id = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["control_id"]

    def __str__(self):
        return f"{self.control_id} - {self.title}"


class PromptTemplate(models.Model):
    """
    Reusable prompt snippets/templates.
    These can be referenced by PolicyTemplate or used ad-hoc.
    """
    name = models.CharField(max_length=150, unique=True)
    template = models.TextField(help_text="Use placeholders like {POLICY_NAME}, {CONTROL_SUMMARY}, {ORG_NAME}, {MAX_WORDS}")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    default_model = models.CharField(max_length=100, default="gpt-4o-mini")

    def __str__(self):
        return self.name


class PolicyTemplate(models.Model):
    """
    Represents a named policy/procedure that maps to multiple Annex A controls.
    Example: 'Information Security Policy' -> maps to A.5.1, A.5.2, A.5.3
    """
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    controls = models.ManyToManyField(Control, related_name="policy_templates", blank=True)
    prompt_template = models.ForeignKey(PromptTemplate, on_delete=models.SET_NULL, null=True, blank=True,
                                        help_text="Optional prompt template to use for this policy")
    default_max_words = models.PositiveIntegerField(default=600)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def control_list(self):
        return ", ".join([c.control_id for c in self.controls.all()])

    def control_count(self):
        return self.controls.count()

    def __str__(self):
        return self.name


class GeneratedPolicy(models.Model):
    """
    Stores a single generation result. If a policy maps to multiple controls,
    those controls are linked via `mapped_controls`.
    """
    template = models.ForeignKey(PolicyTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255)
    generated_text = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    model_used = models.CharField(max_length=100)
    tokens = models.IntegerField(null=True, blank=True)
    cost = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
                               help_text="Estimated API cost (currency units)")
    mapped_controls = models.ManyToManyField(Control, related_name="generated_policies", blank=True)
    version = models.PositiveIntegerField(default=1)
    metadata = models.JSONField(null=True, blank=True,
                                help_text="Optional metadata snapshot (prompt, params, org context, etc.)")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} (v{self.version})"


class ValidationResult(models.Model):
    """
    Stores automated validation results for a GeneratedPolicy.
    The `result` JSON can include per-control flags, scores, missing elements, etc.
    """
    generated_policy = models.OneToOneField(GeneratedPolicy, on_delete=models.CASCADE, related_name="validation")
    result = models.JSONField(default=dict, blank=True,
                              help_text="Validation output: e.g. {'coverage': 0.85, 'per_control': {...}}")
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Validation for {self.generated_policy_id} - {self.created_at.isoformat()}"

# add at top imports if not present
from django.contrib.auth import get_user_model
User = get_user_model()

# ---- CompanyProfile model ----
class CompanyProfile(models.Model):
    """
    Stores organizational context that can be reused when generating policies.
    One profile per user (optional) but can be extended for multi-profile support.
    """
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name="company_profile")
    org_name = models.CharField(max_length=200, default="Amoeba Labs Pvt. Ltd.")
    industry = models.CharField(max_length=120, blank=True, help_text="e.g., SaaS, FinTech, Healthcare")
    size = models.CharField(max_length=32, choices=[("small","Small"),("medium","Medium"),("large","Large")], default="small")
    office_country = models.CharField(max_length=120, blank=True)
    office_city = models.CharField(max_length=120, blank=True)
    has_physical_office = models.BooleanField(default=True)
    deployment = models.CharField(max_length=40, choices=[("cloud","Cloud"),("on-prem","On-Prem"),("hybrid","Hybrid")], default="cloud")
    critical_assets = models.TextField(blank=True, help_text="Comma-separated key assets, e.g., 'Customer PII, Source Code'")
    employment_model = models.CharField(max_length=64, choices=[("fulltime","Full-time"),("mix","Mixed"),("contractors","Contractors heavy")], default="mix")
    background_checks = models.CharField(max_length=64, choices=[("all","All"),("ft_only","Full-time only"),("none","None")], default="ft_only")
    security_training_frequency = models.CharField(max_length=64, choices=[("annual","Annual"),("quarterly","Quarterly"),("ad_hoc","Ad-hoc")], default="annual")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def brief(self):
        parts = [self.org_name]
        if self.office_city and self.office_country:
            parts.append(f"{self.office_city}, {self.office_country}")
        return " — ".join(parts)

    def to_prompt_block(self):
        """
        Return a compact string suitable for inserting into prompts.
        """
        lines = [
            f"Organization: {self.org_name}",
            f"Industry: {self.industry or 'N/A'}",
            f"Size: {self.size}",
            f"Location: {self.office_city or 'N/A'}, {self.office_country or 'N/A'}",
            f"Physical office: {'Yes' if self.has_physical_office else 'No'}",
            f"Deployment: {self.deployment}",
            f"Critical assets: {self.critical_assets or 'N/A'}",
            f"Employment model: {self.employment_model}",
            f"Background checks: {self.background_checks}",
            f"Training frequency: {self.security_training_frequency}",
        ]
        return "\n".join(lines)

    def __str__(self):
        return f"CompanyProfile({self.owner}) - {self.org_name}"

