from django.urls import path
from .views import (
    PolicyTemplateListView,
    PolicyTemplateCreateView,
    PolicyTemplateUpdateView,
    GenerateByTemplateView,
    BatchGenerateView,
    PolicyDetailView,
    HistoryView,
    GeneratedPolicyEditView,
)

app_name = "doc_generator"

urlpatterns = [

    # --- Policy Template Management ---
    path("templates/", 
         PolicyTemplateListView.as_view(), 
         name="template_list"),

    path("templates/add/", 
         PolicyTemplateCreateView.as_view(), 
         name="template_create"),

    path("templates/<int:pk>/edit/", 
         PolicyTemplateUpdateView.as_view(), 
         name="template_edit"),

    # --- Single Policy Generation (from a mapped policy template) ---
    path("generate/", 
         GenerateByTemplateView.as_view(), 
         name="generate"),

    # --- Batch Generation ---
    path("batch-generate/", 
         BatchGenerateView.as_view(), 
         name="batch_generate"),

    # --- Generated Policy Views ---
    path("policy/<int:pk>/", 
         PolicyDetailView.as_view(), 
         name="policy_detail"),

    path("policy/<int:pk>/edit/", 
         GeneratedPolicyEditView.as_view(), 
         name="policy_edit"),

    # --- History (list of user-generated policies) ---
    path("history/", 
         HistoryView.as_view(), 
         name="history"),

]

