from django import forms


class BatchUploadForm(forms.Form):
    batch_name = forms.CharField(required=False)
    zip_file = forms.FileField()

class FilterForm(forms.Form):
    state = forms.ChoiceField(required=True)
    city = forms.ChoiceField(required=False)
    payer = forms.ChoiceField(required=False)

    def __init__(self, *args, state_choices=None, city_choices=None, payer_choices=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["state"].choices = [("", "Select State")] + list(state_choices or [])
        self.fields["city"].choices = [("", "All Cities")] + list(city_choices or [])

        self.fields["state"].widget.attrs.update({"class": "form-select"})
        self.fields["city"].widget.attrs.update({"class": "form-select"})


from .models import MasterHospital, MasterPatient


class RecommendationFilterForm(forms.Form):
    state = forms.ChoiceField(required=False)
    city = forms.ChoiceField(required=False)
    gender = forms.ChoiceField(required=False)
    payer_name = forms.ChoiceField(required=False)

    def __init__(self, *args, payer_choices=None, **kwargs):
        super().__init__(*args, **kwargs)

        state_choices = [('', 'All States')] + [
            (s['state'], s['state'])
            for s in MasterHospital.objects.exclude(state__isnull=True).exclude(state='').values('state').distinct().order_by('state')
        ]
        self.fields['state'].choices = state_choices

        selected_state = None
        if self.data.get('state'):
            selected_state = self.data.get('state')
        elif self.initial.get('state'):
            selected_state = self.initial.get('state')

        city_qs = MasterHospital.objects.exclude(city__isnull=True).exclude(city='')
        if selected_state:
            city_qs = city_qs.filter(state=selected_state)

        city_choices = [('', 'All Cities')] + [
            (c['city'], c['city'])
            for c in city_qs.values('city').distinct().order_by('city')
        ]
        self.fields['city'].choices = city_choices

        gender_choices = [('', 'All Genders')] + [
            (g['gender'], g['gender'])
            for g in MasterPatient.objects.exclude(gender__isnull=True).exclude(gender='').values('gender').distinct().order_by('gender')
        ]
        self.fields['gender'].choices = gender_choices

        payer_choices = payer_choices or []
        self.fields['payer_name'].choices = [('', 'All Payers')] + payer_choices

        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'form-control'
            })



from django import forms
from django.contrib.auth.models import User


class DeveloperLoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)


class DeveloperRequestAccessForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email"]

    def clean(self):
        cleaned = super().clean()
        pwd = cleaned.get("password")
        cpwd = cleaned.get("confirm_password")
        if pwd and cpwd and pwd != cpwd:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned