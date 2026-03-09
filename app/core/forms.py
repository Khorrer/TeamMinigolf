from django import forms
from django.core.exceptions import ValidationError

from .models import Course, Player, Session


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["name", "active"]


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["name", "location", "holes_count"]

    def clean_holes_count(self):
        val = self.cleaned_data["holes_count"]
        if self.instance.pk and self.instance.holes_count != val:
            if self.instance.sessions.exists():
                raise ValidationError(
                    "Bahnanzahl kann nicht geändert werden, wenn bereits Spieltage existieren."
                )
        return val


class SessionCreateForm(forms.ModelForm):
    players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.filter(active=True),
        widget=forms.CheckboxSelectMultiple,
        label="Spieler",
    )

    class Meta:
        model = Session
        fields = ["course", "played_at", "season", "notes"]
        widgets = {
            "played_at": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class ScoreForm(forms.Form):
    strokes = forms.IntegerField(min_value=1, max_value=10, required=False)
