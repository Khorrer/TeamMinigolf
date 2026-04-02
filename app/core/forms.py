from django import forms
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date
import json

from .best_player import BEST_PLAYER_NAME, is_best_player_name
from .models import Course, Player, Session


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["name", "active"]

    def clean_name(self):
        name = self.cleaned_data["name"]
        if is_best_player_name(name):
            raise ValidationError(f"'{BEST_PLAYER_NAME}' ist reserviert und wird automatisch verwaltet.")
        return name


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["name", "location", "holes_count"]

    def clean_holes_count(self):
        val = self.cleaned_data["holes_count"]
        if self.instance.pk and self.instance.holes_count != val:
            if self.instance.sessions.exists():
                raise ValidationError("Bahnanzahl kann nicht geändert werden, wenn bereits Spieltage existieren.")
        return val


class SessionCreateForm(forms.ModelForm):
    players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.filter(active=True).exclude(name__iexact=BEST_PLAYER_NAME),
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


class AIScoreImportForm(forms.Form):
    chatgpt_output = forms.CharField(
        label="Paste ChatGPT JSON Output",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 14,
                "placeholder": '{\n  "course": "Course Name",\n  "date": "YYYY-MM-DD",\n  "players": []\n}',
            }
        ),
    )

    def clean_chatgpt_output(self):
        raw_value = self.cleaned_data["chatgpt_output"].strip()
        normalized = self._strip_code_fences(raw_value)

        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid JSON: {exc.msg}")

        if not isinstance(payload, dict):
            raise ValidationError("JSON root must be an object.")

        required_fields = ["course", "date", "players"]
        missing_fields = [field for field in required_fields if field not in payload]
        if missing_fields:
            raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}.")

        course_name = payload.get("course")
        if not isinstance(course_name, str) or not course_name.strip():
            raise ValidationError("Field 'course' must be a non-empty string.")

        parsed_date = parse_date(str(payload.get("date", "")))
        if parsed_date is None:
            raise ValidationError("Field 'date' must be in format YYYY-MM-DD.")

        players = payload.get("players")
        if not isinstance(players, list) or not players:
            raise ValidationError("Field 'players' must be a non-empty list.")

        normalized_players = []
        seen_names = set()
        for index, player_data in enumerate(players, start=1):
            if not isinstance(player_data, dict):
                raise ValidationError(f"Player #{index} must be an object.")

            player_name = player_data.get("name")
            if not isinstance(player_name, str) or not player_name.strip():
                raise ValidationError(f"Player #{index}: 'name' is required.")

            normalized_name = player_name.strip()
            key = normalized_name.casefold()
            if key in seen_names:
                raise ValidationError(f"Duplicate player in JSON: '{normalized_name}'.")
            seen_names.add(key)

            scores = player_data.get("scores")
            if not isinstance(scores, list):
                raise ValidationError(f"Player '{normalized_name}': 'scores' must be a list.")

            if len(scores) != 18:
                raise ValidationError(f"Player '{normalized_name}' must have exactly 18 scores.")

            parsed_scores = []
            for hole_number, score in enumerate(scores, start=1):
                if not isinstance(score, int) or isinstance(score, bool):
                    raise ValidationError(f"Player '{normalized_name}' hole {hole_number}: score must be a number.")
                if score < 1 or score > 7:
                    raise ValidationError(
                        f"Player '{normalized_name}' hole {hole_number}: score must be between 1 and 7."
                    )
                parsed_scores.append(score)

            normalized_players.append({"name": normalized_name, "scores": parsed_scores})

        self.cleaned_data["parsed_payload"] = {
            "course": course_name.strip(),
            "date": parsed_date,
            "players": normalized_players,
        }
        return raw_value

    @staticmethod
    def _strip_code_fences(value):
        if value.startswith("```"):
            lines = value.splitlines()
            if len(lines) >= 2 and lines[-1].strip() == "```":
                return "\n".join(lines[1:-1]).strip()
        return value
