# apps/work_categories/forms.py
from django import forms
from .models import WorkCategory

class BulkSubCategoryForm(forms.Form):
    category = forms.ModelChoiceField(
        queryset=WorkCategory.objects.filter(is_active=True),
        empty_label="Select Work Category",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    subcategory_names = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 15,
            'cols': 50,
            'placeholder': 'Enter subcategory names, one per line:\n\nExample:\nElectrician\nPlumber\nCarpenter\nPainter'
        }),
        help_text="Enter one subcategory name per line. Each name will be used as both name and display_name."
    )