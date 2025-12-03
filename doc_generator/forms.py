from django import forms
from .models import PolicyTemplate, GeneratedPolicy

class GenerateByTemplateForm(forms.Form):
    policy_template = forms.ModelChoiceField(
        queryset=PolicyTemplate.objects.all(),
        required=True,
        label="Policy Template"
    )
    org_name = forms.CharField(required=False, initial="Amoeba Labs", label="Organization Name")
    org_size = forms.ChoiceField(choices=[("small","Small"),("medium","Medium"),("large","Large")], initial="small")
    environment = forms.ChoiceField(choices=[("cloud","Cloud"),("on-prem","On-Prem"),("hybrid","Hybrid")], initial="cloud")
    max_words = forms.IntegerField(required=False, initial=600, min_value=100, max_value=5000)

    def clean(self):
        cleaned = super().clean()
        # ensure max_words falls back to template default if not provided
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
    org_name = forms.CharField(required=False, initial="Amoeba Labs", label="Organization Name")
    org_size = forms.ChoiceField(choices=[("small","Small"),("medium","Medium"),("large","Large")], initial="small")
    environment = forms.ChoiceField(choices=[("cloud","Cloud"),("on-prem","On-Prem"),("hybrid","Hybrid")], initial="cloud")
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

