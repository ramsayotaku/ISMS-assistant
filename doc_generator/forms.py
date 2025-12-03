from django import forms
from .models import PolicyTemplate, GeneratedPolicy, CompanyProfile


class GenerateByTemplateForm(forms.Form):
    # Company/context fields (explicit)
    org_name = forms.CharField(required=False, initial="Amoeba Labs Pvt. Ltd.", label="Organization Name")
    industry = forms.CharField(required=False, label="Industry", help_text="e.g., SaaS, FinTech")
    size = forms.ChoiceField(choices=[("small","Small"),("medium","Medium"),("large","Large")], initial="small")
    office_country = forms.CharField(required=False, label="Office Country")
    office_city = forms.CharField(required=False, label="Office City")
    has_physical_office = forms.BooleanField(required=False, initial=True, label="Has physical office")
    deployment = forms.ChoiceField(choices=[("cloud","Cloud"),("on-prem","On-Prem"),("hybrid","Hybrid")], initial="cloud")
    critical_assets = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows":3}), label="Critical assets", help_text="Comma-separated")
    employment_model = forms.ChoiceField(choices=[("fulltime","Full-time"),("mix","Mixed"),("contractors","Contractors heavy")], initial="mix")
    background_checks = forms.ChoiceField(choices=[("all","All"),("ft_only","Full-time only"),("none","None")], initial="ft_only")
    security_training_frequency = forms.ChoiceField(choices=[("annual","Annual"),("quarterly","Quarterly"),("ad_hoc","Ad-hoc")], initial="annual")
    save_profile = forms.BooleanField(required=False, initial=False, label="Save this context to my profile")

    policy_template = forms.ModelChoiceField(queryset=PolicyTemplate.objects.all(), required=True, label="Policy Template")
    max_words = forms.IntegerField(required=False, initial=600, min_value=100, max_value=5000)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("max_words") and cleaned.get("policy_template"):
            cleaned["max_words"] = cleaned["policy_template"].default_max_words
        return cleaned


class BatchGenerateForm(forms.Form):
    templates = forms.ModelMultipleChoiceField(
        queryset=PolicyTemplate.objects.all(),
        required=True,
        label="Select Policy Templates",
        widget=forms.CheckboxSelectMultiple
    )
    max_words = forms.IntegerField(required=False, initial=600, min_value=100, max_value=5000)


class PolicyTemplateForm(forms.ModelForm):
    class Meta:
        model = PolicyTemplate
        fields = ["name", "description", "controls", "prompt_template", "default_max_words"]
        widgets = {
            "controls": forms.CheckboxSelectMultiple,
        }


class GeneratedPolicyEditForm(forms.ModelForm):
    class Meta:
        model = GeneratedPolicy
        fields = ["title", "generated_text"]
        widgets = {
            "generated_text": forms.Textarea(attrs={"rows": 20, "cols": 100}),
        }

