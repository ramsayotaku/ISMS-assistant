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

