from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, FormView, UpdateView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.utils import timezone
import logging

from .models import PolicyTemplate, GeneratedPolicy, PromptTemplate, CompanyProfile, Control
from .forms import GenerateByTemplateForm, BatchGenerateForm, PolicyTemplateForm, GeneratedPolicyEditForm
from .services.openai_client import OpenAIClient
from .services.prompt_builder import build_prompt

logger = logging.getLogger(__name__)

class PolicyTemplateListView(LoginRequiredMixin, ListView):
    model = PolicyTemplate
    template_name = "doc_generator/policytemplate_list.html"
    context_object_name = "templates"
    paginate_by = 20


class PolicyTemplateCreateView(LoginRequiredMixin, CreateView):
    model = PolicyTemplate
    form_class = PolicyTemplateForm
    template_name = "doc_generator/policytemplate_form.html"
    success_url = reverse_lazy("doc_generator:template_list")


class PolicyTemplateUpdateView(LoginRequiredMixin, UpdateView):
    model = PolicyTemplate
    form_class = PolicyTemplateForm
    template_name = "doc_generator/policytemplate_form.html"
    success_url = reverse_lazy("doc_generator:template_list")

class BatchGenerateView(LoginRequiredMixin, FormView):
    template_name = "doc_generator/batch_generate.html"
    form_class = BatchGenerateForm
    success_url = reverse_lazy("doc_generator:history")

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
    template_name = "doc_generator/policy_detail.html"
    context_object_name = "policy"


class HistoryView(LoginRequiredMixin, ListView):
    model = GeneratedPolicy
    template_name = "doc_generator/history.html"
    context_object_name = "policies"
    paginate_by = 25

    def get_queryset(self):
        # show user their own generations (admins may override later)
        qs = super().get_queryset()
        return qs.filter(created_by=self.request.user).order_by("-created_at")


class GeneratedPolicyEditView(LoginRequiredMixin, UpdateView):
    model = GeneratedPolicy
    form_class = GeneratedPolicyEditForm
    template_name = "doc_generator/policy_edit.html"

    def get_success_url(self):
        messages.success(self.request, "Policy updated.")
        return reverse_lazy("doc_generator:policy_detail", kwargs={"pk": self.object.pk})


class GenerateByTemplateView(LoginRequiredMixin, FormView):
    """
    FormView to generate a policy from a PolicyTemplate.
    - Form: GenerateByTemplateForm (includes company/context fields and save_profile boolean)
    - On success: creates GeneratedPolicy (with mapped_controls) and redirects to policy_detail
    """
    template_name = "doc_generator/generate_by_template.html"
    form_class = GenerateByTemplateForm
    success_url = reverse_lazy("doc_generator:history")

    def _build_control_summary(self, controls):
        """Return a concise control summary string for inclusion in the prompt."""
        lines = []
        for c in controls:
            # include id, title, and first 140 chars of description if present
            if c.description:
                lines.append(f"- {c.control_id}: {c.title} — {c.description[:140].strip()}")
            else:
                lines.append(f"- {c.control_id}: {c.title}")
        return "\n".join(lines) if lines else "No mapped controls."

    def _select_prompt_template(self, ptemplate):
        """
        Choose prompt template text and default model name.
        Preference order:
          1) PolicyTemplate.prompt_template (FK)
          2) First PromptTemplate in DB (global default)
          3) built-in fallback prompt
        Returns (prompt_text, model_name)
        """
        if ptemplate.prompt_template:
            return ptemplate.prompt_template.template, (ptemplate.prompt_template.default_model or "gpt-4o-mini")
        default_prompt = PromptTemplate.objects.first()
        if default_prompt:
            return default_prompt.template, (default_prompt.default_model or "gpt-4o-mini")

        # fallback prompt
        fallback = (
            "SYSTEM: You are an ISO/IEC 27001 policy writer. Produce a professional corporate policy.\n\n"
            "USER: Draft the policy titled: {POLICY_NAME} for {ORG_NAME}.\n\n"
            "Company context:\n{COMPANY_CONTEXT}\n\n"
            "The policy must satisfy these Annex A controls:\n{CONTROL_SUMMARY}\n\n"
            "Context fields: org_size={ORG_SIZE}, environment={ENVIRONMENT}.\n"
            "Required sections: Purpose, Scope, Policy Statement, Roles & Responsibilities, Monitoring & Review, References.\n"
            "Tone: formal, precise. Limit to {MAX_WORDS} words.\n\n"
            "Output: include a 'Control trace' section mapping paragraphs to the controls listed above."
        )
        return fallback, "gpt-4o-mini"

    def form_valid(self, form):
        # --- gather template & basic params ---
        ptemplate = form.cleaned_data["policy_template"]
        max_words = form.cleaned_data.get("max_words") or ptemplate.default_max_words

        # --- collect company/context fields from the form ---
        ctx = {
            "org_name": form.cleaned_data.get("org_name"),
            "industry": form.cleaned_data.get("industry"),
            "size": form.cleaned_data.get("size"),
            "office_country": form.cleaned_data.get("office_country"),
            "office_city": form.cleaned_data.get("office_city"),
            "has_physical_office": bool(form.cleaned_data.get("has_physical_office")),
            "deployment": form.cleaned_data.get("deployment"),
            "critical_assets": form.cleaned_data.get("critical_assets"),
            "employment_model": form.cleaned_data.get("employment_model"),
            "background_checks": form.cleaned_data.get("background_checks"),
            "security_training_frequency": form.cleaned_data.get("security_training_frequency"),
        }

        # --- optionally save or update CompanyProfile for the user ---
        cp = None
        if form.cleaned_data.get("save_profile") and self.request.user.is_authenticated:
            try:
                cp, created = CompanyProfile.objects.get_or_create(owner=self.request.user)
                # update fields safely
                for k, v in ctx.items():
                    if v is not None:
                        setattr(cp, k, v)
                cp.save()
            except Exception as e:
                logger.exception("Failed to save CompanyProfile: %s", e)
                messages.warning(self.request, "Could not save your company profile (see logs).")
        else:
            # prefer an existing saved profile if present and form did not request explicit save
            try:
                cp = self.request.user.company_profile
            except (CompanyProfile.DoesNotExist, AttributeError):
                cp = None

        # --- prepare prompt context block (prefer saved profile) ---
        if cp:
            company_context_block = cp.to_prompt_block()
            org_name = cp.org_name or ctx.get("org_name") or "Amoeba Labs"
        else:
            # build inline prompt block from form values
            org_name = ctx.get("org_name") or "Amoeba Labs"
            company_context_block = "\n".join([
                f"Organization: {org_name}",
                f"Industry: {ctx.get('industry') or 'N/A'}",
                f"Size: {ctx.get('size') or 'N/A'}",
                f"Location: {ctx.get('office_city') or 'N/A'}, {ctx.get('office_country') or 'N/A'}",
                f"Physical office: {'Yes' if ctx.get('has_physical_office') else 'No'}",
                f"Deployment: {ctx.get('deployment') or 'N/A'}",
                f"Critical assets: {ctx.get('critical_assets') or 'N/A'}",
            ])

        # --- build control summary ---
        controls = list(ptemplate.controls.all())
        control_summary = self._build_control_summary(controls)

        # --- pick prompt template ---
        prompt_tpl, model_name = self._select_prompt_template(ptemplate)

        # --- format the final prompt (use safe formatting) ---
        try:
            prompt = prompt_tpl.format(
                POLICY_NAME=ptemplate.name,
                CONTROL_SUMMARY=control_summary,
                COMPANY_CONTEXT=company_context_block,
                ORG_NAME=org_name,
                ORG_SIZE=ctx.get("size"),
                ENVIRONMENT=ctx.get("deployment"),
                MAX_WORDS=max_words
            )
        except Exception as e:
            logger.exception("Prompt formatting failed: %s", e)
            messages.error(self.request, "Failed to build the prompt. Check prompt template placeholders.")
            return redirect(self.success_url)

        # --- call LLM (OpenAI client) ---
        client = OpenAIClient()
        try:
            # generous max_tokens but bounded for cost/length
            result = client.generate(prompt, max_tokens=1500)
        except Exception as e:
            logger.exception("LLM generation failed: %s", e)
            messages.error(self.request, f"Policy generation failed: {str(e)}")
            return redirect(self.success_url)

        # result should be a dict with 'text', 'tokens', 'model' keys
        generated_text = result.get("text") or result.get("message") or ""
        tokens = result.get("tokens")
        model_used = result.get("model") or model_name

        # --- persist GeneratedPolicy and mapped controls ---
        try:
            gp = GeneratedPolicy.objects.create(
                template=ptemplate,
                title=ptemplate.name,
                generated_text=generated_text,
                created_by=self.request.user,
                created_at=timezone.now(),
                model_used=model_used,
                tokens=tokens,
                cost=(tokens or 0) / 1000.0,  # crude cost estimate (adjust if using real pricing)
                metadata={
                    "prompt": prompt,
                    "org_context": {**ctx, "used_profile": bool(cp)},
                    "llm_result_meta": {k: v for k, v in result.items() if k not in ("text",)}
                }
            )
            if controls:
                gp.mapped_controls.set(controls)
            gp.save()
        except Exception as e:
            logger.exception("Failed to save GeneratedPolicy: %s", e)
            messages.error(self.request, "Failed to save generated policy (see logs).")
            return redirect(self.success_url)

        messages.success(self.request, f"Policy generated: {gp.title}")
        return redirect("doc_generator:policy_detail", pk=gp.id)

