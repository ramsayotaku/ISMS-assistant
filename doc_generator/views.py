from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, FormView, UpdateView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.utils import timezone

from .models import PolicyTemplate, GeneratedPolicy, PromptTemplate
from .forms import GenerateByTemplateForm, BatchGenerateForm, PolicyTemplateForm, GeneratedPolicyEditForm
from .services.openai_client import OpenAIClient
from .services.prompt_builder import build_prompt


class PolicyTemplateListView(LoginRequiredMixin, ListView):
    model = PolicyTemplate
    template_name = "generator/policytemplate_list.html"
    context_object_name = "templates"
    paginate_by = 20


class PolicyTemplateCreateView(LoginRequiredMixin, CreateView):
    model = PolicyTemplate
    form_class = PolicyTemplateForm
    template_name = "generator/policytemplate_form.html"
    success_url = reverse_lazy("generator:template_list")


class PolicyTemplateUpdateView(LoginRequiredMixin, UpdateView):
    model = PolicyTemplate
    form_class = PolicyTemplateForm
    template_name = "generator/policytemplate_form.html"
    success_url = reverse_lazy("generator:template_list")


class GenerateByTemplateView(LoginRequiredMixin, FormView):
    template_name = "generator/generate_by_template.html"
    form_class = GenerateByTemplateForm
    success_url = reverse_lazy("generator:history")

    def form_valid(self, form):
        ptemplate = form.cleaned_data["policy_template"]
        org_name = form.cleaned_data.get("org_name") or "Amoeba Labs"
        org_size = form.cleaned_data.get("org_size") or "small"
        environment = form.cleaned_data.get("environment") or "cloud"
        max_words = form.cleaned_data.get("max_words") or ptemplate.default_max_words

        # Build control summary
        controls = ptemplate.controls.all()
        control_lines = []
        for c in controls:
            line = f"- {c.control_id}: {c.title}"
            if c.description:
                # keep description short
                line += f" — {c.description[:180].strip()}"
            control_lines.append(line)
        control_summary = "\n".join(control_lines) if control_lines else "No mapped controls."

        # Determine prompt template: use PolicyTemplate.prompt_template if present, else default PromptTemplate
        if ptemplate.prompt_template:
            prompt_tpl = ptemplate.prompt_template.template
            model_name = ptemplate.prompt_template.default_model or "gpt-4o-mini"
        else:
            default_prompt = PromptTemplate.objects.first()
            if default_prompt:
                prompt_tpl = default_prompt.template
                model_name = default_prompt.default_model or "gpt-4o-mini"
            else:
                # fallback simple prompt
                prompt_tpl = (
                    "SYSTEM: You are an ISO/IEC 27001 policy writer.\n\n"
                    "USER: Draft the policy: {POLICY_NAME} for {ORG_NAME}.\n"
                    "Controls:\n{CONTROL_SUMMARY}\n\n"
                    "Context: org_size={ORG_SIZE}, environment={ENVIRONMENT}.\n"
                    "Required sections: Purpose, Scope, Policy Statement, Roles & Responsibilities, Monitoring & Review.\n"
                    "Tone: formal. Limit to {MAX_WORDS} words.\n\n"
                    "Output: include a 'Control trace' mapping paragraphs to controls."
                )
                model_name = "gpt-4o-mini"

        prompt = prompt_tpl.format(
            POLICY_NAME=ptemplate.name,
            CONTROL_SUMMARY=control_summary,
            ORG_NAME=org_name,
            ORG_SIZE=org_size,
            ENVIRONMENT=environment,
            MAX_WORDS=max_words
        )

        client = OpenAIClient()
        try:
            result = client.generate(prompt, max_tokens=1200)
        except Exception as e:
            messages.error(self.request, f"Generation failed: {str(e)}")
            return redirect(self.success_url)

        gp = GeneratedPolicy.objects.create(
            template=ptemplate,
            title=ptemplate.name,
            generated_text=result.get("text") or result.get("message") or "",
            created_by=self.request.user,
            created_at=timezone.now(),
            model_used=result.get("model", model_name),
            tokens=result.get("tokens"),
            cost=(result.get("tokens") or 0) / 1000.0,  # crude cost estimate
            metadata={
                "prompt": prompt,
                "org_context": {"org_name": org_name, "org_size": org_size, "environment": environment},
                "llm_result_meta": {k: v for k, v in result.items() if k not in ("text",)}
            }
        )
        gp.mapped_controls.set(controls)
        gp.save()

        messages.success(self.request, f"Policy generated: {gp.title}")
        return redirect("generator:policy_detail", pk=gp.id)


class BatchGenerateView(LoginRequiredMixin, FormView):
    template_name = "generator/batch_generate.html"
    form_class = BatchGenerateForm
    success_url = reverse_lazy("generator:history")

    def form_valid(self, form):
        templates = form.cleaned_data["templates"]
        org_name = form.cleaned_data.get("org_name") or "Amoeba Labs"
        org_size = form.cleaned_data.get("org_size") or "small"
        environment = form.cleaned_data.get("environment") or "cloud"
        max_words = form.cleaned_data.get("max_words")

        client = OpenAIClient()
        created = []
        errors = []

        for ptemplate in templates:
            # reuse logic from GenerateByTemplateView to build prompt
            controls = ptemplate.controls.all()
            control_lines = []
            for c in controls:
                line = f"- {c.control_id}: {c.title}"
                if c.description:
                    line += f" — {c.description[:150].strip()}"
                control_lines.append(line)
            control_summary = "\n".join(control_lines) if control_lines else "No mapped controls."

            prompt_tpl = ptemplate.prompt_template.template if ptemplate.prompt_template else (PromptTemplate.objects.first().template if PromptTemplate.objects.exists() else None)
            if not prompt_tpl:
                prompt_tpl = (
                    "SYSTEM: You are an ISO/IEC 27001 policy writer.\n\n"
                    "USER: Draft the policy: {POLICY_NAME} for {ORG_NAME}.\n"
                    "Controls:\n{CONTROL_SUMMARY}\n\n"
                    "Context: org_size={ORG_SIZE}, environment={ENVIRONMENT}.\n"
                    "Required sections: Purpose, Scope, Policy Statement, Roles & Responsibilities, Monitoring & Review.\n"
                    "Tone: formal. Limit to {MAX_WORDS} words.\n\n"
                    "Output: include a 'Control trace' mapping paragraphs to controls."
                )

            prompt = prompt_tpl.format(
                POLICY_NAME=ptemplate.name,
                CONTROL_SUMMARY=control_summary,
                ORG_NAME=org_name,
                ORG_SIZE=org_size,
                ENVIRONMENT=environment,
                MAX_WORDS=max_words or ptemplate.default_max_words
            )

            try:
                result = client.generate(prompt, max_tokens=1200)
            except Exception as e:
                errors.append(f"{ptemplate.name}: {str(e)}")
                continue

            gp = GeneratedPolicy.objects.create(
                template=ptemplate,
                title=ptemplate.name,
                generated_text=result.get("text") or "",
                created_by=self.request.user,
                created_at=timezone.now(),
                model_used=result.get("model", "gpt-4o-mini"),
                tokens=result.get("tokens"),
                cost=(result.get("tokens") or 0) / 1000.0,
                metadata={"prompt": prompt}
            )
            gp.mapped_controls.set(controls)
            gp.save()
            created.append(gp)

        if created:
            messages.success(self.request, f"Created {len(created)} policies.")
        if errors:
            messages.warning(self.request, f"Errors: {'; '.join(errors)}")

        return redirect(self.success_url)


class PolicyDetailView(LoginRequiredMixin, DetailView):
    model = GeneratedPolicy
    template_name = "generator/policy_detail.html"
    context_object_name = "policy"


class HistoryView(LoginRequiredMixin, ListView):
    model = GeneratedPolicy
    template_name = "generator/history.html"
    context_object_name = "policies"
    paginate_by = 25

    def get_queryset(self):
        # show user their own generations (admins may override later)
        qs = super().get_queryset()
        return qs.filter(created_by=self.request.user).order_by("-created_at")


class GeneratedPolicyEditView(LoginRequiredMixin, UpdateView):
    model = GeneratedPolicy
    form_class = GeneratedPolicyEditForm
    template_name = "generator/policy_edit.html"

    def get_success_url(self):
        messages.success(self.request, "Policy updated.")
        return reverse_lazy("generator:policy_detail", kwargs={"pk": self.object.pk})

